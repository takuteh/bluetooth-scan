# bluetooth-scan

Raspberry Pi で BLE（Bluetooth Low Energy）デバイスを検出・監視するための Python アプリケーションである。

指定した BLE デバイスの検出状態を監視し、一定時間検出されなかった場合に「見失い」、その後再び検出された場合に「復帰」と判定する。状態の変化に応じて Slack 通知を送信し、MQTT メッセージを発行する。

## 概要

本アプリケーションは、Raspberry Pi の Bluetooth アダプターを利用して BLE デバイスをスキャンする。

主な機能は以下のとおりである。

- BLE デバイスの検出
- MAC アドレスによる監視対象の指定
- 複数デバイスの監視
- デバイスの検出・消失状態の管理
- Slack による状態変化の通知
- MQTT によるイベント送信

現在は Autolock との連携を想定しているが、BLE デバイスの検出処理を独立させることで、ほかの用途にも利用できる構成を目指している。

監視対象のデバイスが **10 分間検出されなかった場合に見失いと判定し、その後、再び検出された時点で復帰と判定する**。見失い・復帰の状態変化に応じて、Slack 通知(incomming-webhook)と MQTT メッセージの送信を行う。

## 動作環境

- Raspberry Pi
- Raspberry Pi OS または Bluetooth に対応した Linux ディストリビューション
- Python 3
- BlueZ
- Bluetooth アダプター（内蔵または USB 接続）

※ Bluetooth アダプターや OS の構成によって、必要な設定が異なる場合がある。

## インストール

### 1. 必要なパッケージのインストール

パッケージ一覧を更新し、Python と Bluetooth 関連のパッケージをインストールする。

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv bluetooth bluez
```

Bluetooth サービスを有効化する。

```bash
sudo systemctl enable --now bluetooth
```

### 2. Bluetooth の動作確認

Bluetooth コントローラーが認識されていることを確認する。

```bash
bluetoothctl list
```

コントローラーが表示されない場合は、Bluetooth アダプターや OS の設定を確認する。

続いて、Bluetooth の状態を確認する。

```bash
bluetoothctl show
```

`Powered: yes` と表示されていれば、Bluetooth コントローラーは有効である。

Bluetooth が無効になっている場合は、必要に応じて以下のコマンドでブロックを解除する。

```bash
sudo rfkill unblock bluetooth
```

続いて、Bluetooth の対話モードを起動する。

```bash
bluetoothctl
```

対話モードで以下を実行し、周囲の BLE デバイスが検出されることを確認する。

```text
power on
scan on
```

確認後、スキャンを停止して終了する。

```text
scan off
quit
```

### 3. リポジトリの取得

リポジトリを取得し、作業ディレクトリに移動する。

```bash
git clone https://github.com/takuteh/bluetooth-scan.git
cd bluetooth-scan
```

### 4. Python 仮想環境の作成

Python の依存関係をシステム環境から分離するため、仮想環境を作成する。

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5. Python ライブラリのインストール

`requirements.txt` に記載されたライブラリをインストールする。

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 設定

監視対象の BLE デバイスや MQTT ブローカー、Slack の通知先などは、環境変数で設定する。

主な設定項目は以下のとおりである。

| 環境変数 | 説明 |
|---|---|
| `TARGET_ADDRS` | 監視対象の BLE デバイスの MAC アドレス。複数指定する場合はカンマ区切り |
| `MQTT_BROKER` | MQTT ブローカーのアドレス |
| `MQTT_BROKER_2` | 2 つ目の MQTT ブローカーのアドレス |
| `MQTT_PORT` | MQTT ブローカーのポート番号 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook の URL |

※ 実際に必要な環境変数は、アプリケーションの実装に合わせて設定する。

### 環境変数の設定

環境変数の設定は `env.sh` にまとめる。

`env.sh` には、監視対象の MAC アドレス、Slack Incoming Webhook の URL、MQTT ブローカーのアドレスなどを設定する。秘密情報を含むため、Git リポジトリにはコミットしない。

環境変数の設定例を以下に示す。

```bash
#!/bin/bash

export TARGET_ADDRS="XX:XX:XX:XX:XX:XX"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export MQTT_BROKER="192.168.1.10"
export MQTT_BROKER_2="192.168.1.11"
export MQTT_PORT="1883"
```

上記のアドレスは設定例であり、実際の環境に合わせて変更する。

手動で起動する場合は、`env.sh` を読み込んでからアプリケーションを実行する。

```bash
source env.sh
python main.py
```

systemd サービスから起動する場合は、サービスファイルで `env.sh` を読み込むように設定する。

## 起動方法

### 手動での起動

Python 仮想環境を有効化し、環境変数を読み込んでからアプリケーションを起動する。

```bash
source .venv/bin/activate
source env.sh
python main.py
```

終了する場合は `Ctrl+C` を押す。

### systemd による起動

常時稼働させる場合は、systemd サービスとして登録する構成を想定している。

サービスファイルでは、Python 仮想環境内の Python 実行ファイルを指定し、`env.sh` から環境変数を読み込むように設定する。

これにより、起動時に環境変数を手動で設定することなく、アプリケーションを実行できる。

## Docker 化について

当初は Docker コンテナでの実行を検討していた。

しかし、コンテナ内から BLE デバイスをスキャンする際に、Bluetooth の管理コマンドが失敗する問題が発生した。ホスト側ではスキャンできる一方、コンテナ内では正常にスキャンできない状態となったため、現時点では Docker 化を保留している。

まずは Raspberry Pi に直接インストールする構成で動作を安定させ、必要に応じてコンテナ化を再検討する。

## 今後の課題

- BLE スキャン処理の安定化
- 設定項目の整理
- MQTT 連携の汎用化
- ログ出力の改善
- Docker 化
- Kubernetes 上での実行方法の検討