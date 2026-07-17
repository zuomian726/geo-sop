# GEO-SOP Metric Definitions

V1.0 uses the following definitions in the desktop dashboard, cloud dashboard,
and exports. A missing value is shown as `-`; GEO-SOP does not invent a value
when the collected answer does not contain enough evidence.

## Brand exposure

- An answer is exposed when at least one configured brand exposure keyword is
  found as a literal substring in the collected answer text.
- `Brand exposure rate = exposed answers / collected answers x 100%`.
- One answer counts once in the exposure rate even when it contains several
  configured keywords. Each matched keyword is retained for keyword analysis.
- Matching is literal. Add common spelling, language, abbreviation, and letter
  case variants as separate exposure keywords when they should all count.

## Explicit rank

- A rank is included only when the platform answer contains a structured list
  that the collector can parse and the ranked name matches a configured brand
  keyword.
- `Explicit rank average = sum of matched explicit ranks / matched ranks`.
- A brand mention without an explicit parsed rank is not treated as rank 1 and
  is not estimated from unrelated list items.

## References

- A reference is a source URL returned with an AI answer and captured by the
  platform collector.
- Reference count is the number of captured source items for the answer.
- Reference domains are normalized host names deduplicated across the selected
  result set. The ranking view counts captured citations; the trend view counts
  citations on each collection date.
- A GEO manuscript is marked as cited only when a captured reference can be
  matched to one of its configured article URLs.

## Sentiment

- Local sentiment applies the selected keyword rules to the collected answer
  and returns positive, neutral, or negative. It is deterministic and does not
  require an external API.
- AI sentiment is optional. It uses the user's configured OpenAI-compatible or
  Anthropic-compatible provider and preserves the returned label, score, and
  explanation.
- AI sentiment never replaces the source answer. When the provider is missing,
  times out, or returns invalid data, the local result remains available.

## GEO health score

The compact health score is a navigation aid, not an industry benchmark. It
combines brand exposure, monitored platform coverage, reference-source breadth,
and data completeness. Users should use the underlying metrics and evidence for
decisions instead of comparing the score across unrelated projects.
