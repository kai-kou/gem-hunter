# telemetry/cost-data

Claude Code セッションの月次コスト集計（機械生成テレメトリ）専用のデータブランチにゃ。

- 書き込みは `tools/commit_cost_telemetry.py`（Stop hook から 1 日 1 回）のみ。
- main とはマージしない（コード履歴を汚さない・#242）。
- 参照: `git show origin/telemetry/cost-data:content/analytics/cost_monthly/YYYY-MM.json`
