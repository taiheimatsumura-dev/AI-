"""
AI・競合ニュース自動収集＆送信スクリプト

GitHub Actions の cron から毎朝実行されることを想定した、Cowork とは
完全に独立したスクリプトです。Anthropic API (Claude + 組み込みWeb検索ツール)
でニュースを収集・要約し、Resend の REST API でメールを送信します。

必要な環境変数（GitHub Secretsに設定）:
  ANTHROPIC_API_KEY - console.anthropic.com で発行するAPIキー
  RESEND_API_KEY     - Resendのsending_access APIキー
"""

import os
import sys
import json
import datetime
import requests
import anthropic

# ==== 設定 ====
FROM_ADDRESS = "noreply@gaiasystem.co.jp"
TO_ADDRESSES = [
    "taihei.matsumura@gaiasystem.co.jp",
    "taihei0827@icloud.com",
    "yoshiko.tsuruta@gaiasystem.co.jp",
]
MODEL = "claude-sonnet-5"

CATEGORIES_PROMPT = """\
あなたは「AI・競合ニュース自動収集＆送信」の日次タスクを実行します。
今日の日付を確認し、直近24〜48時間以内の日本語・英語ニュースを対象に、
Web検索ツールを使って以下のカテゴリごとに関連ニュースを収集してください。
各カテゴリで見つからなければ「該当ニュースなし」としてください。
誇張や推測を避け、実際に見つかった記事のタイトル・要約（1〜2文）・情報源URL・日付のみを記載してください。

【収集カテゴリと検索キーワード】
1. 自社関連ニュース: 「株式会社ガイアシステム」「株式会社ガイアサイン」「フラクタルグループ」「AIM8 アイムエイト」
2. AI業界全般: 生成AI、LLM、AIエージェント関連の主要ニュース（国内外）
3. 研修・人材育成競合: 「株式会社リンクアンドモチベーション」「株式会社インソース」「株式会社Schoo」「株式会社アクシア」「株式会社みらい創世舎」
4. 美容部員派遣・紹介競合: 「ミス・パリ」「iDA アイ・ディ・エー」「メイクスキャリア」「テンプスタッフ 美容部員」
5. 介護職員派遣・紹介競合: 「レバウェル介護 レバレジーズメディカルケア」「かいご畑 ニッソーネット」
6. AI経営支援（新規事業AIM8の競合）: 「中小企業 AI経営コンサル」「生成AI 導入支援 サービス」「AI伴走支援 経営」
7. 地方創生・移住支援: 「地方創生 移住支援 民間企業」「DMO 地域再生 コンサル」

収集が終わったら、カテゴリ見出し（1〜7）ごとに箇条書きでまとめたメール本文を、
必ず次のJSON形式のみで出力してください（JSON以外の文章やコードブロック記号は一切含めないこと）。

{
  "subject": "AI・競合ニュースダイジェスト YYYY/MM/DD",
  "html": "<h2>...</h2>...(HTML本文全体)",
  "text": "プレーンテキスト本文全体"
}
"""


def research_and_compose() -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today = datetime.date.today().strftime("%Y/%m/%d")
    user_prompt = f"今日の日付は {today} です。\n\n{CATEGORIES_PROMPT}"

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 20}],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # 最終テキストブロックを結合して取得
    final_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    # JSON部分を抽出してパース（念のため前後の余分な文字を除去）
    start = final_text.find("{")
    end = final_text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON not found in model output:\n{final_text}")

    payload = json.loads(final_text[start : end + 1])
    for key in ("subject", "html", "text"):
        if key not in payload:
            raise ValueError(f"Missing key '{key}' in model output")
    return payload


def send_email(subject: str, html: str, text: str) -> None:
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "from": FROM_ADDRESS,
            "to": TO_ADDRESSES,
            "subject": subject,
            "html": html,
            "text": text,
        },
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")
    print(f"Email sent: {resp.json()}")


def main():
    try:
        payload = research_and_compose()
        send_email(payload["subject"], payload["html"], payload["text"])
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
