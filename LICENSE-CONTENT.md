# Licensing of figures and input texts

The MIT license in `LICENSE` covers the code in this repository
(`run_paperbanana.py`, `scripts/`). Figures and text excerpts are licensed
separately, as follows.

## Generated figures

`results/*/generated_final.png` were produced by the PaperBanana pipeline
(OpenAI models) from the inputs in `inputs/`, without manual edits. They are
released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Note that the TARA and Turkish ASR figures are derived from method sections
licensed as listed below; reuse should respect those terms as well.

## Original figures and method-section excerpts

The `original_*.png` crops, the left half of each
`compare_original_vs_generated.png`, and the text in `inputs/` come from the
following arXiv papers co-authored by Davut Emre Taşar. They are reproduced
with attribution under each paper's arXiv license:

| Folder | Paper | Authors | License |
|---|---|---|---|
| `qcp-multioutput-conformal` | *Quantum-Enhanced Conformal Methods for Multi-Output Uncertainty: A Holistic Exploration and Experimental Analysis*, [arXiv:2501.10414](https://arxiv.org/abs/2501.10414) | D. E. Taşar | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `tara-conformal-quantum` | *TARA: Test-by-Adaptive-Ranks for Quantum Anomaly Detection with Conformal Prediction Guarantees*, [arXiv:2512.04016](https://arxiv.org/abs/2512.04016) | D. E. Taşar, C. Öcal Taşar | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |
| `tr-asr-whisper-wav2vec2` | *Performance Comparison of Pre-trained Models for Speech-to-Text in Turkish: Whisper-Small and Wav2Vec2-XLS-R-300M*, [arXiv:2307.04765](https://arxiv.org/abs/2307.04765) | Ö. B. Mercan, S. Çepni, D. E. Taşar, Ş. Ozan | [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) |

The method-section texts in `inputs/` are excerpts, lightly condensed and reformatted to
plain text (math written inline) so they can be passed to the pipeline.

## Upstream code

PaperBanana / PaperVizAgent is licensed under Apache-2.0 by its authors. This
repository does not include any of its source code; `scripts/setup.sh` clones
it at a pinned commit.
