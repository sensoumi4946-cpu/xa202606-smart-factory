from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any

from analytics.agv_guard import AgvGuard
from analytics.fault_predictor import FaultPredictor
from analytics.hazard_reasoner import HazardReasoner
from analytics.policy_verifier import verify_controller
from analytics.safety_controller import SafetyController




def _quiet_logs() -> None:
    logging.getLogger("analytics").setLevel(logging.ERROR)
    logging.getLogger("analytics.hazard_reasoner").setLevel(logging.ERROR)
    logging.getLogger("analytics.safety_controller").setLevel(logging.ERROR)
    logging.getLogger("analytics.policy_verifier").setLevel(logging.ERROR)


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title.encode("gbk", errors="replace")))


def run_fault_prediction() -> dict[str, Any]:
    _section("[1] 故障预测")
    predictor = FaultPredictor()

    print("  输入：MQ-2 上报 CO，线性上升 3.5 ppm/s；报警阈值 35 ppm")
    print()
    print(f"  {'t (s)':>6}  {'CO (ppm)':>10}  {'预测':<44}")
    print("  " + "-" * 66)

    records = []
    first_warning = None
    for i in range(11):
        t = float(i)
        value = 5.0 + i * 3.5
        prediction = predictor.push("esp32_02_mq2", "co", value, timestamp=t)
        if prediction and prediction.seconds_to_threshold:
            text = (
                f"{prediction.seconds_to_threshold:.1f}s 后达到阈值 "
                f"(R²={prediction.r_squared:.3f}, {prediction.confidence})"
            )
            if first_warning is None:
                first_warning = {
                    "t": t,
                    "value": value,
                    "lead_time_s": prediction.seconds_to_threshold,
                    "r_squared": prediction.r_squared,
                }
        elif prediction:
            text = "已超过阈值"
        else:
            text = "窗口未满"
        print(f"  {t:>6.0f}  {value:>10.1f}  {text:<44}")
        records.append({"t": t, "value": value, "prediction": text})

    print()
    if first_warning:
        print(
            f"  首次预警 t={first_warning['t']:.0f}s，CO={first_warning['value']:.1f} ppm，尚未超阈值"
        )
        print(
            f"  提前量 {first_warning['lead_time_s']:.1f} s，R²={first_warning['r_squared']:.3f}"
        )
    return {"records": records, "first_warning": first_warning}


def run_hazard_alert() -> dict[str, Any]:
    _section("[2] 危险警报")
    reasoner = HazardReasoner()

    print("  输入：t=100s MQ-2/Modbus 上报 CO=50 ppm；t=102s DHT22/MQTT 上报温度=45 ℃")
    print("  两个数值单独看都只是普通超标。")
    print()

    alerts = reasoner.observe(
        "esp32_02_mq2", "gas", "modbus", [{"type": "co", "value": 50.0}], timestamp=100.0
    )
    print(f"  t=100s  CO 超标            告警数 {len(alerts)}")

    alerts = reasoner.observe(
        "esp32_01_dht22",
        "temp_humidity",
        "mqtt",
        [{"type": "temperature", "value": 45.0}],
        timestamp=102.0,
    )
    print(f"  t=102s  温度同时超标      告警数 {len(alerts)}")
    print()

    payload = None
    for alert in alerts:
        payload = alert.to_dict()
        print(f"  规则 {alert.rule_name}（{alert.label_zh}），等级 {alert.severity}")
        print(f"  子系统 {'、'.join(alert.subsystems)}")
        print(f"  协议   {' + '.join(p.upper() for p in alert.protocols)}")
        for link in alert.chain():
            print(f"    {link}")
        print(f"  处置建议 {alert.recommended_action}")

    print()
    print("  两条数据来自不同设备、不同协议，映射到同一本体属性后才进入同一条规则。")
    return {"alert": payload}


def run_agv() -> dict[str, Any]:
    _section("[3] AGV 避障")
    guard = AgvGuard()

    print("  输入：AGV 接近障碍物；制动加速度取 45 cm/s²，反应时间取 0.35 s（待实测标定）")
    print()
    print(f"  {'t (s)':>6}  {'距离 (cm)':>10}  {'接近速度':>10}  {'制动距离':>10}  {'决策':<12}")
    print("  " + "-" * 66)

    distances = [(0.0, 300.0), (1.0, 210.0), (2.0, 120.0), (3.0, 60.0), (4.0, 25.0), (5.0, 12.0)]
    records = []
    first_stop = None
    for t, d in distances:
        decision = guard.push_distance("agv_01", d, timestamp=t)
        action = decision.action or "—"
        print(
            f"  {t:>6.0f}  {d:>10.0f}  {decision.closing_rate_cm_s:>10.1f}  "
            f"{decision.braking_distance_cm:>10.1f}  {decision.level:<8}{action}"
        )
        if decision.level == "stop" and first_stop is None:
            first_stop = {
                "t": t,
                "distance_cm": d,
                "braking_distance_cm": decision.braking_distance_cm,
                "reason": decision.reason,
            }
        records.append(
            {
                "t": t,
                "distance_cm": d,
                "closing_rate": decision.closing_rate_cm_s,
                "braking_distance": decision.braking_distance_cm,
                "level": decision.level,
                "action": decision.action,
            }
        )

    print()
    if first_stop:
        print(
            f"  停车指令在 {first_stop['distance_cm']:.0f} cm 处下发，"
            f"当时制动距离 {first_stop['braking_distance_cm']:.0f} cm。"
        )
        print("  若按固定 15 cm 阈值停车，此速度下已来不及。")
    return {"records": records, "first_stop": first_stop}


def run_verification() -> dict[str, Any]:
    _section("[4] 安全策略验证")
    controller = SafetyController()
    certificate = verify_controller(controller)

    print(f"  策略数      {certificate.policy_count}")
    print(f"  策略对      {certificate.pair_count}")
    print(f"  求解次数    {certificate.checks_run}")
    print(f"  求解器      Z3 {certificate.solver_version}")
    print(f"  结果        {'通过' if certificate.verified else '未通过'}")
    print(f"  指纹        {certificate.fingerprint[:32]}...")
    print()
    print(f"  {certificate.summary_zh()}")

    if certificate.conflicts:
        print()
        for conflict in certificate.conflicts:
            print(f"  {conflict.explanation_zh}")
    return certificate.to_dict()


def run_all(output: Path | None) -> dict[str, Any]:
    _quiet_logs()
    random.seed(20260817)
    results = {
        "fault_prediction": run_fault_prediction(),
        "hazard_alert": run_hazard_alert(),
        "agv_avoidance": run_agv(),
        "policy_verification": run_verification(),
    }

    _section("小结")
    warning = results["fault_prediction"]["first_warning"]
    alert = results["hazard_alert"]["alert"]
    stop = results["agv_avoidance"]["first_stop"]
    cert = results["policy_verification"]

    print(
        f"  故障预测   提前 {warning['lead_time_s']:.1f} s，R²={warning['r_squared']:.3f}"
        if warning
        else "  故障预测   未触发"
    )
    print(
        f"  危险警报   {len(alert['subsystems'])} 个子系统 / "
        f"{len(alert['protocols'])} 种协议 -> {alert['label_zh']}"
        if alert
        else "  危险警报   未触发"
    )
    print(
        f"  AGV 避障   {stop['distance_cm']:.0f} cm 处停车，制动距离 "
        f"{stop['braking_distance_cm']:.0f} cm"
        if stop
        else "  AGV 避障   未触发"
    )
    print(
        f"  策略验证   {cert['policy_count']} 条 / {cert['checks_run']} 次求解 / "
        f"{'无冲突' if cert['verified'] else str(len(cert['conflicts'])) + ' 处冲突'}"
    )
    print()
    print("  注：AGV 制动参数为设定值，硬件到位后需实测标定。")
    print()

    if output:
        output.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  结果已写入 {output}")
        print()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="XA-202606 analytics check")
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()
    run_all(Path(args.json) if args.json else None)


if __name__ == "__main__":
    main()
