# Enketo validation checklist

| ID | Check | Mode | Evidence | Status |
|---|---|---|---|---|
| ENK-01 | Published form opens in the approved browser | Witnessed | Screenshot/browser record | [ ] |
| ENK-02 | Required questions, constraints and repeats behave as specified | Hybrid | Automated form test plus review | [ ] |
| ENK-03 | New submission reaches Central with the expected XML | Automated | Central XML/hash comparison | [ ] |
| ENK-04 | Editing a retained submission shows the expected changed fields | Witnessed/Hybrid | Central activity/API evidence | [ ] |
| ENK-05 | Change reason/comment is entered and linked to the edit stack | Hybrid | Central activity and Sentinel audit record | [ ] |
| ENK-06 | Browser/session interruption does not silently overwrite source data | Witnessed | Controlled interruption record | [ ] |
