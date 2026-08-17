# project_state_revision_stale fixture

用于测试 state_revision 防 stale 机制：
- state._revision = 15（当前最新）
- 测试时注入 `_expected_revision = 10`（陈旧的预期）
- 预期：P5 state_revision patch 检测到 revision 不匹配，报 BLOCKER

注意：此 fixture 本身不"违规"，它只是提供一个干净 baseline。
真正的 stale 检查通过 test 注入 _expected_revision 触发。
