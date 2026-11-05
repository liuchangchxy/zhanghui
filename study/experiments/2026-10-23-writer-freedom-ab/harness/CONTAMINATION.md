{
  "bug": "_natural_node dropped the action clause of every 主体|动作|结果 node in lean prompts",
  "effect": "arm B Writer never saw the required method/action for each node",
  "judge_citations": {
    "ch7": "both judges: B draft used single-station interpolation, missing the 邻站 requirement",
    "ch6": "judge XY: B did not deliver the 交出设备型号变更记录 beat",
    "ch10": "judge YX: B's 年份连续性缺口 read as 月内空白"
  },
  "contaminated_artifacts": [
    "_pre-fix/draft_B_ch10.md",
    "_pre-fix/draft_B_ch6.md",
    "_pre-fix/draft_B_ch7.md",
    "_pre-fix/prompt_B_ch10.txt",
    "_pre-fix/prompt_B_ch6.txt",
    "_pre-fix/prompt_B_ch7.txt"
  ],
  "remedy": "renderer fixed, prompt_B re-sealed, all three arm B chapters re-drafted from scratch"
}