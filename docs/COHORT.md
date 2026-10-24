# Cohort selection and coverage

The cohorts are curated topic lists, not a randomized sample or an automatic discovery of related articles. Each final topic must have all 50 daily API observations in its event window.

During source validation:

- `Eclipse_glasses` returned 46 of 50 requested days. `Solar_viewer`, the relevant established article title, returned a complete series.
- `Corona` was replaced with `Stellar_corona` to remove ambiguity about the astronomical subject.
- `Titan_submersible_implosion` returned 17 days and `OceanGate` returned 20 days in the historical window. Neither can support the specified 28-day pre-event baseline. They were replaced by established related topics `Underwater_acoustics` and `Pressure_vessel`.
- The Titan constellation anchors on `Wreck_of_the_Titanic`, an established related article with a complete baseline.

Missing observations are not interpreted as zero and are never synthesized. This complete-case choice introduces selection bias: newly created or rarely visited articles may be excluded, even if they became highly important during an event. The resulting dashboard describes these curated cohorts only.

The application colors nodes by curated subject categories. Temporal cluster IDs are computed separately using Spark MLlib and are shown in the inspector and table.
