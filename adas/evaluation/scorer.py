"""
Algorithmic scoring for evaluator dimensions that do not require model calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations

try:
    from .models import EvaluationRequest, FeedbackVideoSnapshot, VideoRecord
    from .topic_terms import extract_topic_terms
except ImportError:
    from evaluation.models import EvaluationRequest, FeedbackVideoSnapshot, VideoRecord
    from evaluation.topic_terms import extract_topic_terms


def _normalize_reaction(reaction: str | None) -> float:
    if reaction is None:
        return 5.0

    normalized = reaction.strip().lower()
    if normalized in {"up", "thumbs_up", "like", "liked", "positive", "👍"}:
        return 10.0
    if normalized in {"down", "thumbs_down", "dislike", "disliked", "negative", "👎"}:
        return 0.0
    return 5.0


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _age_hours(published_at: str) -> float:
    return max(
        (_parse_timestamp(published_at) - datetime.now(timezone.utc)).total_seconds() / -3600,
        0.0,
    )


def _is_future_timestamp(published_at: str) -> bool:
    return _parse_timestamp(published_at) > datetime.now(timezone.utc)


def _extract_topic_terms(video: VideoRecord) -> set[str]:
    return extract_topic_terms(
        title=video.title,
        description=video.description,
        query_matched=video.query_matched,
        tags=video.tags,
    )


def _extract_snapshot_topic_terms(snapshot: FeedbackVideoSnapshot) -> set[str]:
    return extract_topic_terms(
        title=snapshot.title,
        description=snapshot.description,
        query_matched=snapshot.query_matched,
        tags=snapshot.tags,
    )


def _pairwise_jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


@dataclass(frozen=True, slots=True)
class _HistoricalFeedbackSignal:
    video_id: str
    reaction_score: float
    snapshot: FeedbackVideoSnapshot


_MIN_ALIGNMENT_SIMILARITY = 0.25

# Feature similarity weights for the alignment heuristic.
# Channel identity is the strongest signal (a channel the user liked/disliked
# is a reliable predictor). Topic overlap and duration closeness are secondary.
_CHANNEL_WEIGHT = 0.4
_TOPIC_WEIGHT = 0.4
_DURATION_WEIGHT = 0.2


def _duration_similarity(left_seconds: int, right_seconds: int) -> float:
    if left_seconds <= 0 or right_seconds <= 0:
        return 0.0
    difference = abs(left_seconds - right_seconds)
    return max(0.0, 1.0 - (difference / 1800.0))


def _channel_similarity(video: VideoRecord, snapshot: FeedbackVideoSnapshot) -> float:
    if video.channel_id and snapshot.channel_id and video.channel_id == snapshot.channel_id:
        return 1.0
    return 0.0


def _feature_similarity(video: VideoRecord, snapshot: FeedbackVideoSnapshot) -> float:
    channel_component = _CHANNEL_WEIGHT * _channel_similarity(video, snapshot)
    topic_component = _TOPIC_WEIGHT * _pairwise_jaccard(
        _extract_topic_terms(video),
        _extract_snapshot_topic_terms(snapshot),
    )
    duration_component = _DURATION_WEIGHT * _duration_similarity(
        video.duration_seconds,
        snapshot.duration_seconds,
    )
    return channel_component + topic_component + duration_component


def _signal_reason(
    video: VideoRecord,
    top_signal: _HistoricalFeedbackSignal,
    weighted_score: float,
) -> str:
    """Describe the blended heuristic result using the strongest single signal for context.

    weighted_score is the actual score used (a blend across all similar signals);
    top_signal identifies the most influential precedent for human-readable detail.
    """
    reasons: list[str] = []
    if _channel_similarity(video, top_signal.snapshot) > 0.0:
        reasons.append("channel match")
    if _pairwise_jaccard(_extract_topic_terms(video), _extract_snapshot_topic_terms(top_signal.snapshot)) > 0.0:
        reasons.append("topic overlap")
    if _duration_similarity(video.duration_seconds, top_signal.snapshot.duration_seconds) > 0.0:
        reasons.append("duration similarity")

    sentiment = (
        "liked"
        if weighted_score > 5.0
        else "disliked"
        if weighted_score < 5.0
        else "neutral"
    )
    return f"{sentiment} precedent via {', '.join(reasons) or 'weak similarity'}"


class AlgorithmicScorer:
    def score_freshness(self, videos: list[VideoRecord]) -> tuple[float, str]:
        if not videos:
            raise ValueError("score_freshness requires at least one selected video.")

        per_video_scores: list[tuple[str, float, float]] = []
        for video in videos:
            if _is_future_timestamp(video.published_at):
                per_video_scores.append((video.video_id, 0.0, 0.0))
                continue

            age_hours = _age_hours(video.published_at)
            base_score = 6.0 if age_hours <= 168 else max(0.0, 6.0 * (720 - age_hours) / 552)
            bonus = max(0.0, 4.0 * (48 - min(age_hours, 48.0)) / 48.0)
            score = min(10.0, base_score + bonus)
            per_video_scores.append((video.video_id, round(age_hours, 2), score))

        average_score = round(
            sum(score for _, _, score in per_video_scores) / len(per_video_scores),
            4,
        )
        detail = "; ".join(
            (
                f"{video.video_id}: future publish timestamp -> 0.0"
                if _is_future_timestamp(video.published_at)
                else f"{video_id}: {hours}h old -> {round(score, 2)}"
            )
            for video, (video_id, hours, score) in zip(videos, per_video_scores, strict=True)
        )
        return average_score, detail

    def score_diversity(self, videos: list[VideoRecord]) -> tuple[float, str]:
        if not videos:
            raise ValueError("score_diversity requires at least one selected video.")
        if len(videos) == 1:
            return 10.0, "Only one selected video; diversity defaults to 10.0."

        unique_channels = len({video.channel_id for video in videos})
        # Normalize channel spread so the score is 0 when all selected videos come
        # from the same channel and 10 when every selected video comes from a different channel.
        channel_score = 10.0 * (unique_channels - 1) / (len(videos) - 1)

        topic_terms = {video.video_id: _extract_topic_terms(video) for video in videos}
        pairwise_similarity = [
            _pairwise_jaccard(topic_terms[left.video_id], topic_terms[right.video_id])
            for left, right in combinations(videos, 2)
        ]
        average_similarity = (
            sum(pairwise_similarity) / len(pairwise_similarity)
            if pairwise_similarity
            else 0.0
        )
        topical_score = 10.0 * (1.0 - average_similarity)
        diversity_score = round((channel_score + topical_score) / 2.0, 4)
        detail = (
            f"{unique_channels}/{len(videos)} unique channels; "
            f"avg topical similarity={round(average_similarity, 4)}"
        )
        return diversity_score, detail

    def score_alignment(
        self,
        request: EvaluationRequest,
        videos: list[VideoRecord],
    ) -> tuple[float, str]:
        if not videos:
            raise ValueError("score_alignment requires at least one selected video.")
        if not request.feedback_history:
            return 5.0, "No feedback history yet; using neutral placeholder score."

        videos_by_id = {video.video_id: video for video in request.videos}
        feedback_by_video: dict[str, list[float]] = {}
        historical_signals: list[_HistoricalFeedbackSignal] = []
        for entry in request.feedback_history:
            for pick in entry.picks:
                reaction_score = _normalize_reaction(pick.reaction)
                feedback_by_video.setdefault(pick.video_id, []).append(reaction_score)
                snapshot = pick.snapshot
                if snapshot is None and pick.video_id in videos_by_id:
                    snapshot = FeedbackVideoSnapshot.from_video(videos_by_id[pick.video_id])
                if snapshot is not None:
                    historical_signals.append(
                        _HistoricalFeedbackSignal(
                            video_id=pick.video_id,
                            reaction_score=reaction_score,
                            snapshot=snapshot,
                        )
                    )

        per_video_scores: list[tuple[str, float, str]] = []
        for video in videos:
            historical_scores = feedback_by_video.get(video.video_id)
            if historical_scores:
                score = sum(historical_scores) / len(historical_scores)
                source = "exact historical match"
            else:
                similar_signals = [
                    (signal, _feature_similarity(video, signal.snapshot))
                    for signal in historical_signals
                    if signal.video_id != video.video_id
                ]
                similar_signals = [
                    (signal, similarity)
                    for signal, similarity in similar_signals
                    if similarity > 0.0
                ]
                if not similar_signals or max(
                    similarity for _, similarity in similar_signals
                ) < _MIN_ALIGNMENT_SIMILARITY:
                    score = 5.0
                    source = "neutral"
                else:
                    total_similarity = sum(similarity for _, similarity in similar_signals)
                    score = sum(
                        signal.reaction_score * similarity
                        for signal, similarity in similar_signals
                    ) / total_similarity
                    top_signal = sorted(
                        similar_signals,
                        key=lambda item: (-item[1], item[0].video_id),
                    )[0][0]
                    source = _signal_reason(video, top_signal, score)
            per_video_scores.append((video.video_id, score, source))

        alignment_score = round(
            sum(score for _, score, _ in per_video_scores) / len(per_video_scores),
            4,
        )
        detail = "; ".join(
            f"{video_id}: {round(score, 2)} ({source})"
            for video_id, score, source in per_video_scores
        )
        return alignment_score, detail

