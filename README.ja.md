# Nemotron Finance Demo

English README: [README.md](README.md)

このリポジトリは、`NVIDIA-Nemotron-Nano-9B-v2-Japanese` と Nemotron Personas Japan を使った金融リサーチ向けデモです。モックモード、vLLM 実運用モード、レポート生成、ペルソナ別フォローアップ会話、履歴再表示までを一式で確認できます。

## 主要ドキュメント

- エージェント向けセットアップ: [`docs/agents/agent-setup.md`](docs/agents/agent-setup.md)
- 構成マップ: [`docs/architecture/code-map.md`](docs/architecture/code-map.md)
- E2E 実行計画: [`docs/testing/e2e-test-plan.md`](docs/testing/e2e-test-plan.md)
- テスト一覧: [`docs/testing/test-matrix.md`](docs/testing/test-matrix.md)

## クイックスタート

### モックモード

```bash
./setup-env.sh --preset local-mock
./start.sh
```

### 実 LLM モード

リポジトリ同梱の reasoning parser を使って vLLM を起動します。

```bash
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese \
  --host 0.0.0.0 --port 8000 \
  --trust-remote-code \
  --max-model-len 131072 \
  --max-num-seqs 64 \
  --gpu-memory-utilization 0.90 \
  --reasoning-parser-plugin backend/vllm_plugins/nemotron_nano_v2_reasoning_parser.py \
  --reasoning-parser nemotron_nano_v2 \
  --mamba-ssm-cache-dtype float32

./setup-env.sh --preset local-vllm
./start.sh
```

## 補足

- 実運用向けの詳細手順は README ではなく `docs/` 配下の agent-first 文書を参照してください。
- 過去の調査メモや古い計画書は `docs/archive/` に移動しています。
