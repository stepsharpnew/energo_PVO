# Design QA — manager MVP

## Evidence

- Source visual truth: `/Users/step/.codex/generated_images/019f79a9-71fa-7e21-9d5e-ab98b2f219c6/call_E1k1Wz3RGUH7GcyMxjYPxwXO.png`
- Initial implementation: `/Users/step/Desktop/projects/Energo_PVO/data/runs/ui-design-qa-20260727/implementation-step-2.png`
- Final implementation: `/Users/step/Desktop/projects/Energo_PVO/data/runs/ui-design-qa-20260727/implementation-step-2-demo.png`
- Final side-by-side comparison, source left / implementation right: `/Users/step/Desktop/projects/Energo_PVO/data/runs/ui-design-qa-20260727/comparison-final-source-left-implementation-right.png`
- Additional job-state evidence: `/Users/step/Desktop/projects/Energo_PVO/data/runs/ui-design-qa-20260727/implementation-job-needs-input.png`
- Mobile evidence: `/Users/step/Desktop/projects/Energo_PVO/data/runs/ui-design-qa-20260727/implementation-mobile-object.png`
- Desktop CSS viewport: `1440 × 1024`, device scale factor `1`.
- Mobile CSS viewport: `390 × 844`, device scale factor `1`.
- Source pixels: `1487 × 1058`.
- Implementation pixels: `1440 × 1024`.
- Density normalization: source resized to `1440 × 1024` for the side-by-side comparison; the near-identical source and target aspect ratios avoid a material crop.
- Compared state: step 2, two required files selected, three optional attachments indicated.

## Full-view comparison

The final implementation preserves the selected concept's dominant structure: a quiet top bar, a persistent four-stage rail, warm mineral canvas, pale-sage active stage, large dark-green heading, two primary upload rows, optional attachments, a recognition strip, and a coral continuation action. The relative proportions of the rail, content column, upload surfaces, and footer actions match the source closely.

## Required fidelity surfaces

- Fonts and typography: `Onest` provides a close Cyrillic grotesk with the required heavy display weight and readable 14–16 px product text. Heading scale, line height, compact labels, and utility text have distinct roles with no clipping.
- Spacing and layout rhythm: desktop rail, header, content width, upload rows, dividers, action row, and vertical rhythm follow the source. Mobile collapses the rail to a horizontally scrollable step strip and the form to one column without hiding the primary action.
- Colors and visual tokens: mineral white, forest ink, pale sage, muted gray, and coral map closely to the selected direction. Contrast remains readable; focus states are visible.
- Image and icon fidelity: file, paperclip, and check icons use Bootstrap Icons rather than custom SVG/CSS drawings. No raster hero or decorative image assets exist in the source.
- Copy and content: manager-facing Russian labels explain what to upload, what is optional, what the agent checks, and why `NEEDS_INPUT` can stop release. Internal implementation terms are avoided.

## Interaction and browser checks

- Object → Files transition tested.
- Help drawer open/close tested.
- Optional attachments disclosure tested.
- Mobile step navigation tested at `390 × 844`.
- Existing `NEEDS_INPUT` job rendered with questions, usage, and status progression.
- Browser console checked: no errors or warnings.
- Native file chooser itself was not automated by the in-app browser. Required file inputs, MIME filters, multipart names, manual validation, and post-selection rendering are covered by code and template tests.

## Comparison history

### Pass 1

- [P2] The initial brand and explanatory copy drifted from the selected visual.
- [P2] The primary continuation action was dark green instead of the source coral.
- [P2] File-type visuals used text marks rather than an icon library.

Fixes:

- Restored the `Пошаговый помощник` identity and the source-aligned preparation copy.
- Made the step-2 primary action coral.
- Replaced text marks with Bootstrap Icons for PDF, XLSX, attachments, and confirmation.
- Added a visual-only `?demo=1` state so design QA can compare the same selected-file state without bypassing real upload validation.

### Pass 2

Post-fix evidence is in `comparison-final-source-left-implementation-right.png`. No actionable P0, P1, or P2 differences remain.

## Follow-up polish

- [P3] The implementation is slightly more compact than the generated source in the lower action area; this keeps the full workflow above the fold and is acceptable for the working MVP.
- [P3] Native file picker automation remains a manual acceptance check because the in-app browser does not expose `setInputFiles`.

## Verification

- `44 passed`
- Skill validation: `Skill is valid!`

final result: passed
