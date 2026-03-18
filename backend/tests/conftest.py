import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import FINANCIAL_EXT_DDL, PERSONA_DDL
from routers import personas


@pytest.fixture()
def seeded_db(tmp_path: Path) -> str:
  db_path = tmp_path / 'personas-test.db'
  conn = sqlite3.connect(db_path)
  conn.executescript(PERSONA_DDL)
  conn.executescript(FINANCIAL_EXT_DDL)

  personas_rows = [
    (
      'p1', '田中太郎', '会社員', None, None, None, None, 'ペルソナ1', '日本',
      '営業', "['営業']", '読書', "['読書']", '昇進', '男', 35, '既婚', '大学卒',
      '会社員', '関東', '都心', '東京都', '日本',
    ),
    (
      'p2', '佐藤花子', '公務員', None, None, None, None, 'ペルソナ2', '日本',
      '事務', "['事務']", '旅行', "['旅行']", '安定', '女', 29, '未婚', '大学卒',
      '公務員', '関東', '都心', '東京都', '日本',
    ),
    (
      'p3', '鈴木一郎', '自営業', None, None, None, None, 'ペルソナ3', '日本',
      '経営', "['経営']", 'ゴルフ', "['ゴルフ']", '事業拡大', '男', 52, '既婚', '高校卒',
      '自営業', '関西', '都市部', '大阪府', '日本',
    ),
    (
      'p4', '高橋陽子', '会社員', None, None, None, None, 'ペルソナ4', '日本',
      '企画', "['企画']", '料理', "['料理']", '転職', '女', 45, '既婚', '大学卒',
      '会社員', '関東', '郊外', '神奈川県', '日本',
    ),
  ]
  conn.executemany(
    'INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    personas_rows,
  )
  conn.executemany(
    'INSERT INTO persona_financial_context VALUES (?, ?, ?, ?, ?, ?, ?)',
    [
      ('p1', '中級者', 'あり', '老後資金', '600-800万円', '1000-3000万円', 'メガバンク'),
      ('p2', '初心者', 'なし', '生活費', '400-600万円', '500-1000万円', 'ネット銀行'),
      ('p3', '専門家', 'あり', '事業承継', '800万円以上', '3000万円以上', '地方銀行'),
      ('p4', '上級者', 'あり', '教育費', '600-800万円', '1000-3000万円', 'メガバンク'),
    ],
  )
  conn.commit()
  conn.close()
  return str(db_path)


@pytest.fixture()
def client(seeded_db: str):
  original_db_path = settings.db_path
  settings.db_path = seeded_db

  app = FastAPI()
  app.include_router(personas.router)

  with TestClient(app) as test_client:
    yield test_client

  settings.db_path = original_db_path
