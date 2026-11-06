# zoho-crm-portfolio

Small, client-neutral tools and notes from real Zoho CRM projects.
Everything here is generic: no customer data, no customer code.

[日本語は下にあります](#日本語)

## Tools

| Tool | What it does |
| --- | --- |
| [deluge-lint](deluge-lint/) | Catches common mistakes in Zoho Deluge scripts — unbalanced brackets, unsupported loops, comments inside `invokeurl`, hardcoded record IDs — before you paste the code into the editor. Python 3.9+, no dependencies. |

### deluge-lint quick start

```bash
cd deluge-lint
python deluge_lint.py examples/bad.dg
python deluge_lint.py path/to/functions/          # scans *.dg recursively
python deluge_lint.py my_function.dg --format json
```

Exit code is `1` when any error is found, so it works in CI or a pre-commit hook.

11 rules, from unbalanced brackets to calls that Deluge does not support. The full list is in [deluge-lint/README.md](deluge-lint/README.md).

The checks are heuristic, not a full Deluge parser. They aim for few false positives, so a clean result does not prove the script will save or run.

## About me

I'm Kotaro, a Zoho CRM developer and consultant in Japan. I design and build Zoho CRM setups for small and mid-sized businesses: Deluge, Client Script, Widgets, API integrations, data migration, and AI features with human approval.

[Website](https://www.kotarosan-nocode.com) · [Upwork](https://www.upwork.com/freelancers/~01a5ef53de58789fdc) · [LinkedIn](https://www.linkedin.com/in/kotaro-izumida-0a57a7399/)

## 日本語

Zoho CRM の実案件で使ってきた道具のうち、お客様の情報を含まないものを公開しています。

- **deluge-lint** — Deluge のコードを Zoho の画面に貼る前に、よくある誤りを見つけます。括弧の閉じ忘れ、Deluge に無い書き方（`while`・C 言語風の `for`・三項演算子）、`invokeurl` の中のコメント、レコード ID の直書きなど。Python 3.9 以上で、追加のインストールは要りません。

調べるのは書き方の誤りだけです。結果に問題が無くても、保存・実行できることまでは保証しません。

Zoho CRM の設計・開発のご相談は [kotarosan-nocode.com](https://www.kotarosan-nocode.com/contact) から。

## License

MIT
