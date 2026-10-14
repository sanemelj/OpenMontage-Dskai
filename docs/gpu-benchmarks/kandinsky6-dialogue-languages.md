# Kandinsky 6.0 Lite — native dialogue by language (2026-10-14)

Dialogue is generated natively inside the clip (video + audio in one pass).
Post-hoc voice replacement + lip-sync (LatentSync 1.6) was tested and rejected:
it produced a visible second mouth while the character's own mouth stayed closed.

Model: Lite-distill (16 steps), Modal L40S, 864×480, 121 frames, seeds 7 and 42.

| Language | Prompt style | Line | Result |
|---|---|---|---|
| English | `He says quietly in English: "..."` | "I never meant to lie to you." | Exact (Whisper en, p=0.91) |
| French | `He says quietly in French: "..."` | "Je n'ai jamais voulu te mentir." | Exact on 2/2 seeds |
| French | `She speaks French, clearly and slowly: "..."` | "Où étais-tu hier soir ?" | Exact on seed 7; "la soirée" on seed 42 |
| Kreyòl | A: standard orthography | "Kote w te ye yè swa?" | Not recognised by Whisper; pending native review |
| Kreyòl | **B: French-style orthography** | "Koté ou té yé, yè swa ?" | **Seed 7 approved by a native speaker** (Whisper misreads it — do not use Whisper to judge Kreyòl) |

## Kreyòl prompt rule (style B)

- Write the line with French accents to steer pronunciation: é for /e/, è for /ɛ/,
  split syllables the model tends to merge ("Koté ou té yé" rather than "Kote w te ye").
- Add: `She speaks Haitian Creole with a Haitian accent, slowly, every syllable clear: "<line>"`
- Add: `Audio: only her clear voice, quiet room tone.` (keeps ambience out of the dialogue
  track; ambience and music are added in the mix).
- Native-speaker review is the acceptance test; success rate per seed is still being measured.
