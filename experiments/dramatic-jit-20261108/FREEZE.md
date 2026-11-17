# Freeze manifest — dramatic JIT A/B (chapter 0004)

All hashes SHA-256 of the exact bytes. A/B raws were generated once and never regenerated.

| file | bytes | SHA-256 |
|---|---:|---|
| `A_current_brief.md` | 5718 | `2d08eb5d521438aa24789183662fd9cffb053044807c51947c364c47bb87141f` |
| `A_current_prompt.txt` | 20435 | `7995b0543f812198a3dde3414878650ca67afa048680db1598d6bf0e3a8c5abf` |
| `A_current_raw.md` | 11412 | `02b61026f47d4571d1345018a114cacea9989a4c91e75f26bcdc2da02e685809` |
| `A_current_status.json` | 663 | `6a47a26a3aa49e81d90583bb70c6f4d730ffb10f5bb8d606f26b41235cfa1962` |
| `B_jit_plan.md` | 16544 | `9809090edf637d7aa15a7c0999b3df6277d28948ee5f846423f807398503ffdf` |
| `B_jit_brief.md` | 8358 | `6f8d4f0428792be585467a34807328cff2caba8d8f0642a9d2736988b247afe8` |
| `B_jit_prompt.txt` | 21067 | `47864b5eb4ba2f3e724f2d1f808bf470badfef524166726bebece776bee9a5db` |
| `B_jit_raw.md` | 12070 | `6e5795d02a79dba138ac3a8c95541124ebc5201ff786317a83020bed076a7ca9` |
| `prompt_diff.txt` | 19176 | `d9e1fb4d70b9d5810e2420c850a5e5f3902c40d7256e1ad684f23235ef893891` |
| `body_diff.txt` | 18938 | `b5aed065d78824763a71b34df2b0cf69421a4e4fb5da91c7416a44edffe5a338` |
| `architecture_diagnosis.md` | 6834 | `f50c32f0bec650b9fd348ed91c71cb46973d444147b7fcc3bc475b2b81077035` |
| `build_b_prompt.py` | 3203 | `fad312dccdb11a4e08ca6fe711f7c14c1c78298ba1208fe4fe86e216d3e99470` |
| `build_blind.py` | 2836 | `7e16ac80d504397883fd801f6b189c7ff86740b3aafb84748634aec9b489f7d4` |
| `blind/judge_common.md` | 4471 | `e5976886840555fd1aa9e4f74d135f2cd7143d3c58b4108880ac02a361125f9c` |
| `blind/blind_key.json` | 455 | `c89a784568bf06f1a7a4e65945814a6c32a836deb7525c6da6216b159d6d2877` |
| `blind/X.md` | 9240 | `8c98fc474fbee089ac91efa9d7118cf712158b84b03605194c865e1067ce5b28` |
| `blind/Y.md` | 9174 | `cdb97f9570c807197e7b11a2eff20bc398a597bb5b7c75d8768eaeba2b15cbe0` |
| `judge/packet_XY.md` | 22942 | `cc77d379618eea81b325f099e58deb7021acdbe521e5581ab6776594df2fbd42` |
| `judge/packet_YX.md` | 22942 | `81d3304f7af72ac35ee4a7b84d8086d475b40c56999bbc4c5cd67457b1505f8d` |
| `judge/judge1_fable.md` | 7541 | `4d3e750a8c506e51a349d4588226252aa3c37af9c1d0d4aee2852e9a2ff7497e` |
| `judge/judge2_opus.md` | 7371 | `41730946d5f3406ab449b64a435c81c14c53961b4e9b8b8afdc7363f8652acd1` |

## Sealed A package

- `package_fingerprint`: `d93a2fde6043671f1a8c0d78a3a0bf8ae842cd1ab5ea4d697615191a4a8b4d42`
- `is_writer_package_stale`: `False`
- `writing_skills_fingerprint`: `1d98a1217e1a9d972e31d1a0f3cd584aeda89e803624352de6a4d948347c1631`
- skills: scene-sequel, character-agency, dialogue-subtext, reader-pull

## Blind key

```json
{
  "mapping": {
    "X": "B",
    "Y": "A"
  },
  "A_current_raw_sha256": "02b61026f47d4571d1345018a114cacea9989a4c91e75f26bcdc2da02e685809",
  "B_jit_raw_sha256": "6e5795d02a79dba138ac3a8c95541124ebc5201ff786317a83020bed076a7ca9",
  "A_prose_sha256": "cdb97f9570c807197e7b11a2eff20bc398a597bb5b7c75d8768eaeba2b15cbe0",
  "B_prose_sha256": "8c98fc474fbee089ac91efa9d7118cf712158b84b03605194c865e1067ce5b28",
  "A_prose_cjk": 2486,
  "B_prose_cjk": 2498
}
```

## Judge positions

- Judge 1 (`fable`): packet XY — X read first.
- Judge 2 (`opus`): packet YX — Y read first.
- Mapping: X = B (JIT), Y = A (Current).

## Known asymmetry (recorded after judging)

The frozen Hard Intent included `不让木盾恢复或凭空换新盾`. That clause is **not** in
`大纲/第1卷-详细大纲.md` chapter 4 and **not** in A's production brief
(`.webnovel/tmp/creative_brief_0004.txt`), which only says the shield cannot be equipped
until repaired. A therefore did not receive this prohibition; B did. Both judges used it as
a hard rule, so the shield-related preference is excluded from the JIT evidence in `REPORT.md`.
