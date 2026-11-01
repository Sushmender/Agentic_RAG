/**
 * frontend/src/utils/relevance.js
 * Utility to format and tier retrieval / reranker relevance scores.
 */

export function formatRelevance(score) {
  if (score == null || Number.isNaN(Number(score))) {
    return {
      pct: 0,
      val: 0,
      label: '0%',
      raw: '0.0000',
      tier: 'low',
    };
  }

  const rawNum = Number(score);
  let val = rawNum;

  // If score is outside [0, 1] (e.g. raw logit from cross-encoder/reranker), map via sigmoid
  if (val < 0 || val > 1) {
    val = 1 / (1 + Math.exp(-val));
  }

  // Clamp to [0, 1]
  val = Math.max(0, Math.min(1, val));
  const pct = Math.round(val * 100);

  // If there is positive relevance but it rounds to 0%, display '<1%' to avoid deceptive 0%
  let label = `${pct}%`;
  if (val > 0 && pct === 0) {
    label = '<1%';
  }

  // Tier color assignment: high (>= 70%), medium (40-69%), low (< 40%)
  // Never show low scores in green/accent
  let tier = 'low';
  if (pct >= 70) {
    tier = 'high';
  } else if (pct >= 40) {
    tier = 'medium';
  }

  return {
    pct,
    val,
    label,
    raw: rawNum.toFixed(4),
    tier, // 'high' | 'medium' | 'low'
  };
}
