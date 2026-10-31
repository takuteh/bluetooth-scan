import os
import time
import logging

import requests
import paho.mqtt.client as mqtt
from bluepy.btle import Scanner, DefaultDelegate


# ============================================================
# 設定
# ============================================================

WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_BROKER_2 = os.getenv("MQTT_BROKER_2")
MQTT_PORT = int(os.getenv("MQTT_PORT"))

MQTT_TOPIC = "/door/open"
CLOSE_TOPIC = "/door/close"

# カンマ区切りで複数の BLE デバイスを指定
TARGET_ADDRS = {
    addr.strip().lower()
    for addr in os.environ["TARGET_ADDRS"].split(",")
    if addr.strip()
}

# デバイスを見失ったと判断するまでの時間（秒）
TIMEOUT = 600

if not TARGET_ADDRS:
    raise ValueError("TARGET_ADDRS に BLE デバイスの MAC アドレスを指定してください")


# ============================================================
# ログ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# Slack 通知
# ============================================================

def send_slack(message):
    """Slack Incoming Webhook で通知する。"""

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"text": message},
            timeout=10,
        )
        response.raise_for_status()

    except requests.RequestException:
        logger.exception("Slack 通知に失敗しました")


# ============================================================
# MQTT
# ============================================================

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(
            "MQTT 接続成功: %s",
            userdata["broker"],
        )
    else:
        logger.error(
            "MQTT 接続失敗: %s rc=%s",
            userdata["broker"],
            rc,
        )


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(
            "MQTT 切断: %s rc=%s",
            userdata["broker"],
            rc,
        )


def create_mqtt_client(broker):
    """MQTT クライアントを作成する。"""

    client = mqtt.Client(
        userdata={"broker": broker},
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # 再接続時の待機時間
    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30,
    )

    client.connect_async(
        broker,
        MQTT_PORT,
        60,
    )

    client.loop_start()

    return client


client = create_mqtt_client(MQTT_BROKER)
client2 = create_mqtt_client(MQTT_BROKER_2)


def publish_message(topic, message):
    """2つの MQTT ブローカーにメッセージを送信する。"""

    for mqtt_client in (client, client2):
        try:
            info = mqtt_client.publish(
                topic,
                message,
                qos=1,
            )

            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(
                    "MQTT publish 受付失敗: topic=%s rc=%s",
                    topic,
                    info.rc,
                )

        except Exception:
            logger.exception(
                "MQTT publish 失敗: topic=%s",
                topic,
            )


# ============================================================
# BLE デバイスの状態管理
# ============================================================

# デバイスごとの最終検知時刻
last_seen = {}

# デバイスごとの見失い状態
lost_flags = {
    addr: False
    for addr in TARGET_ADDRS
}


# ============================================================
# BLE スキャン
# ============================================================

class ScanDelegate(DefaultDelegate):

    def __init__(self):
        super().__init__()

    def handleDiscovery(self, dev, isNewDev, isNewData):

        addr = dev.addr.lower()
        rssi = dev.rssi

        # 監視対象以外は無視
        if addr not in TARGET_ADDRS:
            return

        last_seen[addr] = time.time()

        # 見失っていたデバイスが復帰した場合
        if lost_flags[addr]:
            lost_flags[addr] = False

            logger.info(
                "BLE デバイスが復帰しました: %s RSSI=%s",
                addr,
                rssi,
            )

            send_slack(f"復帰しました: {addr}")

            # 開錠メッセージを送信
            publish_message(
                MQTT_TOPIC,
                '{"app":"MQTT","message":"1","user":"takumi"}',
            )


# ============================================================
# メイン処理
# ============================================================

def main():

    logger.info(
        "BLE スキャン開始。監視対象: %s",
        ", ".join(sorted(TARGET_ADDRS)),
    )

    scanner = Scanner().withDelegate(ScanDelegate())
    delegate = scanner.delegate

    while True:

        # BLE スキャン
        try:
            scanner.scan(1.0)

        except Exception:
            logger.exception("BLE スキャンに失敗しました")
            time.sleep(2)
            continue

        now = time.time()

        # 監視対象を個別に確認
        for addr in TARGET_ADDRS:

            last = last_seen.get(addr)

            # 一度も検知していないデバイスは対象外
            if last is None:
                continue

            # 最終検知から TIMEOUT 秒以上経過した場合
            if now - last > TIMEOUT:

                # すでに見失い通知済みなら何もしない
                if lost_flags[addr]:
                    continue

                lost_flags[addr] = True

                logger.warning(
                    "BLE デバイスを見失いました: %s",
                    addr,
                )

                send_slack(f"見失いました: {addr}")

                # 施錠メッセージを送信
                publish_message(
                    CLOSE_TOPIC,
                    '{"app":"MQTT","message":"1","user":"takumi"}',
                )


if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        logger.info("終了します")

    finally:
        client.loop_stop()
        client2.loop_stop()

        client.disconnect()
        client2.disconnect()
