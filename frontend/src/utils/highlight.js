/**
 * src/utils/highlight.js
 * Supporting sentence extraction and text highlight utilities.
 * - Splits chunk text into sentences
 * - Scores each sentence by token overlap with answer text (and question as tie-breaker)
 * - Selects the top 1 to 2 supporting sentences above threshold
 * - Provides helper to wrap matching sentences in <mark> elements
 */

import React from 'react';

// Common English stop words to filter out before scoring token overlap
const STOP_WORDS = new Set([
  'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'aren\'t',
  'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by',
  'can', 'can\'t', 'cannot', 'could', 'couldn\'t', 'did', 'didn\'t', 'do', 'does', 'doesn\'t', 'doing',
  'don\'t', 'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'hadn\'t', 'has', 'hasn\'t',
  'have', 'haven\'t', 'having', 'he', 'he\'d', 'he\'ll', 'he\'s', 'her', 'here', 'here\'s', 'hers',
  'herself', 'him', 'himself', 'his', 'how', 'how\'s', 'i', 'i\'d', 'i\'ll', 'i\'m', 'i\'ve', 'if',
  'in', 'into', 'is', 'isn\'t', 'it', 'it\'s', 'its', 'itself', 'let\'s', 'me', 'more', 'most',
  'mustn\'t', 'my', 'myself', 'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only', 'or', 'other',
  'ought', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'shan\'t', 'she', 'she\'d',
  'she\'ll', 'she\'s', 'should', 'shouldn\'t', 'so', 'some', 'such', 'than', 'that', 'that\'s',
  'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'there\'s', 'these', 'they',
  'they\'d', 'they\'ll', 'they\'re', 'they\'ve', 'this', 'those', 'through', 'to', 'too', 'under',
  'until', 'up', 'very', 'was', 'wasn\'t', 'we', 'we\'d', 'we\'ll', 'we\'re', 'we\'ve', 'were',
  'weren\'t', 'what', 'what\'s', 'when', 'when\'s', 'where', 'where\'s', 'which', 'while', 'who',
  'who\'s', 'whom', 'why', 'why\'s', 'with', 'won\'t', 'would', 'wouldn\'t', 'you', 'you\'d',
  'you\'ll', 'you\'re', 'you\'ve', 'your', 'yours', 'yourself', 'yourselves',
]);

/**
 * Tokenize a text string into normalized content words (lowercase, stripped punctuation, no stop words).
 */
export function tokenize(text) {
  if (!text || typeof text !== 'string') return [];
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, ' ')
    .replace(/[^\w\s]/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length > 2 && !STOP_WORDS.has(t));
}

/**
 * Split text into distinct sentences while ignoring table rows and anchors.
 */
export function splitSentences(text) {
  if (!text || typeof text !== 'string') return [];
  // Split on sentence-ending punctuation followed by whitespace or on newlines
  const rawSegments = text.split(/(?<=[.!?])\s+|\n+/);
  return rawSegments
    .map((s) => s.trim())
    .filter((s) => s.length > 10 && !s.startsWith('|') && !s.startsWith('<a id='));
}

/**
 * Identify the top 1 to 2 supporting sentences in chunkText based on token overlap
 * with answerText (and questionText as tie-breaker).
 *
 * @param {string} chunkText - Source text
 * @param {string} answerText - Generated answer
 * @param {string} [questionText=''] - User query (tie-breaker)
 * @param {number} [threshold=0.25] - Minimum score threshold to consider a match
 * @returns {string[]} Array of up to 2 best matching sentence strings (or empty)
 */
export function findSupportingSentences(chunkText, answerText, questionText = '', threshold = 0.25) {
  if (!chunkText || !answerText) return [];

  const answerTokens = new Set(tokenize(answerText));
  const questionTokens = new Set(tokenize(questionText));

  if (answerTokens.size === 0) return [];

  const sentences = splitSentences(chunkText);
  if (sentences.length === 0) return [];

  const scored = [];

  for (const sentence of sentences) {
    const sTokens = tokenize(sentence);
    if (sTokens.length === 0) continue;

    const matchedAnswer = sTokens.filter((t) => answerTokens.has(t));
    const matchedDistinct = new Set(matchedAnswer);

    // Require at least 2 distinct content token matches with the answer
    if (matchedDistinct.size < 2) continue;

    const matchedQuestion = sTokens.filter((t) => questionTokens.has(t));
    const score =
      (matchedDistinct.size + matchedAnswer.length * 0.2) / Math.sqrt(sTokens.length) +
      0.15 * new Set(matchedQuestion).size;

    if (score >= threshold) {
      scored.push({
        sentence,
        score,
        matchedDistinct: matchedDistinct.size,
      });
    }
  }

  if (scored.length === 0) return [];

  scored.sort((a, b) => b.score - a.score);

  const results = [scored[0].sentence];

  // Include 2nd best if it scored at least 65% of the top sentence and has >= 2 matches
  if (
    scored.length > 1 &&
    scored[1].score >= scored[0].score * 0.65 &&
    scored[1].matchedDistinct >= 2 &&
    scored[1].sentence !== scored[0].sentence
  ) {
    results.push(scored[1].sentence);
  }

  return results;
}

/**
 * Traverses React children and wraps instances of target sentences with
 * <mark className="source-highlight">. Leaves other nodes untouched.
 */
export function highlightInChildren(children, targets) {
  if (!targets || targets.length === 0) return children;

  return React.Children.map(children, (child) => {
    if (typeof child === 'string') {
      let parts = [{ text: child, isMatch: false }];

      for (const target of targets) {
        if (!target) continue;
        const newParts = [];

        for (const part of parts) {
          if (part.isMatch) {
            newParts.push(part);
            continue;
          }

          const idx = part.text.indexOf(target);
          if (idx !== -1) {
            if (idx > 0) {
              newParts.push({ text: part.text.slice(0, idx), isMatch: false });
            }
            newParts.push({
              text: part.text.slice(idx, idx + target.length),
              isMatch: true,
            });
            if (idx + target.length < part.text.length) {
              newParts.push({
                text: part.text.slice(idx + target.length),
                isMatch: false,
              });
            }
          } else {
            newParts.push(part);
          }
        }
        parts = newParts;
      }

      return parts.map((p, i) =>
        p.isMatch
          ? React.createElement('mark', { key: i, className: 'source-highlight' }, p.text)
          : p.text
      );
    }

    if (React.isValidElement(child) && child.props && child.props.children) {
      return React.cloneElement(child, {
        children: highlightInChildren(child.props.children, targets),
      });
    }

    return child;
  });
}
