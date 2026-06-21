# SAM demo pack — Flow 2 (manual entry)

Demo — Unbundling (NCCI PTP), never-allowed pair
Enter in SAM: 00170 ×1 @ $120.00; 96375 ×1 @ $60.00
Expected: recoverable $60.00, top multiple ≈4.16×
Source: flow2_unbundling_ind0_001 (see MANIFEST.json)

Demo — Quantity (NCCI MUE), over the daily cap
Enter in SAM: 0543U ×4 @ $120.00
Expected: recoverable $90.00
Source: flow2_mue_over_001 (see MANIFEST.json)

Demo — Price benchmark (PFS), strong leverage
Enter in SAM: 52001 ×1 @ $2,476.44 POS 11
Expected: recoverable $0.00, top multiple ≈6.0×
Source: pfs_5x_plus_001 (see MANIFEST.json)
