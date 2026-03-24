# Nemotron Finance Demo

English README: [README.md](README.md)

このリポジトリは、`NVIDIA-Nemotron-Nano-9B-v2-Japanese` と Nemotron Personas Japan を使った金融リサーチ向けデモです。市場調査やイベント展示での利用を想定し、属性でペルソナを絞り込み、複数設問の回答をストリーミングで観察し、レポートを生成し、履歴を引き継いだフォローアップ会話まで確認できます。

## 主な機能

- **ペルソナの絞り込みとサンプリング**: Nemotron Personas データセットを属性条件で絞り込み、調査対象を抽出できます
- **リアルタイム調査ストリーミング**: 複数設問の回答をペルソナごとに順次ストリーミング表示します
- **Thinking Mode**: vLLM の reasoning parser 経由で取得した思考出力を必要に応じて表示できます
- **レポート生成**: 定性的サマリー、極性分析を含む示唆、注目ペルソナの抽出をまとめて生成します
- **フォローアップ会話**: レポート後に個別ペルソナへ追加質問を続けられます
- **履歴の再利用**: 過去の調査実行とフォローアップ状態を履歴ストアから再表示できます
- **モック / 実 vLLM モード**: オフライン開発用のモックと、リポジトリ同梱 parser を使う実 vLLM モードの両方をサポートします

## アーキテクチャ

```text
┌─────────────────────┐    SSE / REST APIs    ┌─────────────────────────────┐
│ フロントエンド       │ ────────────────────► │ バックエンド                │
│ React + TypeScript  │                      │ FastAPI + Python            │
│ Vite ビルド成果物    │ ◄──────────────────── │ 調査 / レポート /           │
│ を backend 配信      │                      │ フォローアップ制御          │
└─────────────────────┘                      │ ペルソナ parquet 読み込み   │
                                             │ SQLite 履歴保存             │
                                             └──────────────┬──────────────┘
                                                            │ OpenAI 互換 API
                                                            ▼
                                             ┌─────────────────────────────┐
                                             │ vLLM                        │
                                             │ Nemotron Nano v2 Japanese   │
                                             │ repo 同梱 reasoning parser  │
                                             └─────────────────────────────┘
```

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
