# FINN project rules

## Research sources and citations
- Research reports may use only company annual reports and earnings call (concall) transcripts. Do not use news, broker notes, research reports, or outside model knowledge.
- Every factual claim in a research report must identify its source document and page. Keep source references attached to the specific claim they support.
- If a claim cannot be supported by the allowed documents, label it as unavailable rather than filling the gap from memory or another source.

## Downloads, sample data, and AI answers
- Cache every file or data payload downloaded from the internet and reuse the cached copy instead of downloading it again.
- Keep representative sample data in the project so the app remains usable when an internet source is unavailable.
- Use the Gemini API for AI features. Persist each AI answer and reuse it for an identical request and source set to avoid repeat cost and delay.

## Coverage and product design
- Build the research flow to work for any Indian listed stock when source data is available; do not hard-code it to the demo companies.
- Design for phones first. Keep the experience simple, clean, and distinctive.
- The challenge has a one-day time limit: favor a small, working, demonstrable app over a broad or fragile feature set.
