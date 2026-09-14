# XA-202606 基于国产操作系统的智慧工厂安全监测控制平台

**团队：Binding Minds**  
**学校：浙江师范大学**  
**赛道：第十五届“挑战杯”揭榜挂帅擂台赛**  

## 团队成员

- Sen Soumi
- MOSLEH ABDUL QUDOOS HAMID MOSLEH
- MHIRA ANASS
- AAKIK MOHAMED
- 季宇轩
- 兰博望

## 项目简介

XA-202606 面向智慧工厂安全生产场景，将 MQTT、REST、Modbus TCP 和 OPC UA 等异构设备统一接入同一数据与安全判断链路。系统以 `bindings.ttl` 作为协议绑定的单一事实来源，将现场载荷统一转换为 `UnifiedMessage`，经过设备绑定校验和 SHACL 语义门禁后写入 SQLite，并进入趋势预测、危害推理、安全控制和审计流程。

Apache Jena Fuseki 用于 RDF/知识图谱与 SPARQL 查询。语义持久化处于非关键路径：Fuseki 暂时不可用时，不应阻断现场数据接入和安全分析主链路。

项目目标不是“再做一个监控大屏”，而是形成：

```text
多协议设备
   ↓
bindings.ttl / 生成适配器
   ↓
UnifiedMessage
   ↓
SHACL 语义门禁
   ↓
SQLite + 分析
   ↓
FaultPredictor / HazardReasoner
   ↓
SafetyController
   ↓
后端签名控制 + 审计
```

## 核心机制

### 1. 本体/绑定驱动的多协议接入

根目录 `bindings.ttl` 保存设备与协议参数，包括：

- device ID / alias
- MQTT Topic / QoS
- Modbus 地址、功能码、缩放系数、字节序
- OPC UA NodeId / namespace
- REST 路径
- 单位、测量类型、轮询周期

生成命令：

```bash
python scripts/generate_adapters.py
python scripts/generate_adapters.py --check
```

对已有测量类型和单位的新设备，主要通过修改 `bindings.ttl` 并重新生成适配器完成接入。新增全新的测量或单位类型时，仍需同步修改 Python 契约、语义映射、本体和测试。

### 2. 统一数据契约

不同协议载荷统一转换为 `UnifiedMessage`。后端的入库、分析、告警、查询和审计模块不直接依赖各协议原始字段。

### 3. SHACL 语义门禁

入站数据先完成绑定/契约校验，再执行 SHACL。非法观测返回 422，并记录拒绝原因，不写入业务数据。

### 4. 预测与实时危害分流

当前实现明确区分预测和实时危害：

- **尚未越阈**：`FaultPredictor` 估计阈值穿越时间；
- **已经越阈**：不继续作为预测事件处理，进入实时危害判断；
- `HazardReasoner` 对跨子系统条件进行组合判断；
- `SafetyController` 根据危害结果生成动作建议并施加冷却/保持约束。

这不是故障概率分类器，不报告没有标签数据支撑的分类准确率。

### 5. 观测面与控制面分离

前端只提交 `ControlRequest`。控制命令由后端完成：

1. 鉴权
2. 持久化
3. HMAC 签名
4. dispatcher 分发
5. ACK 状态更新
6. `command_audit` 审计记录

浏览器端不负责生成命令签名。

## 五类现场子系统

| 设备 | 传感器/功能 | 子系统 | 当前绑定协议 |
|---|---|---|---|
| ESP32_001 | DHT22 温湿度 | temp_humidity | Modbus / MQTT / OPC UA |
| ESP32_002 | 红外对射计数 | counting | REST |
| ESP32_003 | PIR + 继电器 | lighting | REST |
| ESP32_004 | HC-SR04 AGV 距离 | agv | OPC UA |
| ESP32_005 | MQ-2 / MQ-7 | gas | Modbus |

> 上表描述的是当前绑定拓扑。演示环境接入状态和实测结果以《系统测试报告》为准。

## 运行环境

- Python 3.11+
- Node.js 20+
- FastAPI + Uvicorn
- Vue 3 + Vite + ECharts
- SQLite
- Apache Jena Fuseki（可选语义服务）
- Mosquitto（MQTT 场景）
- openEuler 24.03 LTS
- systemd（竞赛目标部署）
- Docker Compose（开发/集成）

## 本地运行

### 安装

```bash
git clone https://github.com/sensoumi4946-cpu/xa202606-smart-factory.git
cd xa202606-smart-factory

python -m venv .venv
source .venv/bin/activate        # Linux
# .venv\Scripts\activate         # Windows

pip install -e shared -e backend -e connectivity -e analytics -e semantic-layer
cd dashboard && npm install && cd ..
```

### 关键环境变量

```bash
API_KEY=your_api_key
COMMAND_SIGNING_KEY=your_command_signing_key
```

可选：

```bash
SEMANTIC_WRITE_ENABLED=true
FUSEKI_ENDPOINT=http://localhost:3030/factory/data
FUSEKI_QUERY_URL=http://localhost:3030/factory/query
```

不要把真实密钥提交到仓库或写死在前端源码中。

### 启动

后端应从仓库根目录启动：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

前端：

```bash
cd dashboard
npm run dev
```

默认开发地址：

- Backend: `8000`
- Dashboard: `5173`
- REST adapter: `8100`
- Mosquitto: `1883`
- Modbus: `1502`
- OPC UA: `4840`
- Fuseki: `3030`

## openEuler 部署

openEuler 24.03 LTS 为当前国产操作系统目标环境。

```bash
sudo bash deploy/openeuler/install.sh
sudoedit /etc/xa202606/backend.env
sudoedit /etc/xa202606/connectivity.env
sudo bash deploy/openeuler/verify.sh
```

绑定或阈值变更后：

```bash
sudo xa202606-reload
```

它会先校验配置，再协调重载绑定及活动适配器。

详细说明见：

```text
deploy/openeuler/README.md
```

## 测试

代码回归：

```bash
python -m pytest backend/tests connectivity/tests semantic-layer/tests analytics/tests shared/tests benchmark/tests validation/tests -q
cd firmware && python -m pytest tests -q && cd ..
cd dashboard && npm test -- --run && npm run build && cd ..
python scripts/generate_adapters.py --check
python scripts/validate_sample_data.py
```

配置验证：

```bash
python validation/run_validation.py
```

测试原则：

- 代码回归不替代现场系统验证；
- 合成 JSON 只用于契约/功能演示，不替代传感器精度证据；
- 无物理执行器证据时，不宣称完成物理控制闭环；
- 未验证的 OPC UA 生产证书链不宣称为生产安全链路。

## 已取得的竞赛测试证据

最终《系统测试报告》记录：

- openEuler 24.03 LTS 服务端实测；
- 演示窗口中五类设备在线；
- 完成 **4 小时持续运行测试**；
- `1440` 个连续进程采样点；
- backend PID 无变化，systemd 重启计数为 0；
- `health / latest / forecast` 各执行 `1440` 次，全部 HTTP 200；
- `semantic refresh / cached` 各执行 `240` 次，全部 HTTP 200；
- CPU 平均 `18.38%`，最大 `49.39%`；
- SQLite `quick_check=ok`。

同时，资源稳定性结论仍为**部分通过/继续观察**：

- RSS 在 4 小时窗口内由约 `106.22 MB` 增至 `283.85 MB`；
- 存在秒级长尾延迟；
- 不能将 4 小时结果外推为 24/48 小时生产 SLA。

## 当前明确边界

尚未完成或不应过度表述的项目：

- 真实执行器物理闭环验收；
- 生产级 OPC UA 证书信任链；
- 可溯源传感器精度标定；
- 标准化 24/48 小时多设备物理闭环耐久测试；
- 独立高并发入库性能基准；
- 设备侧统一时间戳与断网补传时间语义；
- 基于真实标签集的故障概率分类。

## 目录

```text
shared/             统一消息契约
connectivity/       MQTT / REST / Modbus / OPC UA 接入
backend/            FastAPI、入站、存储、安全、控制与审计
semantic-layer/     RDF / SHACL / AAS / SPARQL / Fuseki
analytics/          预测、异常、危害、安全控制
dashboard/          Vue 3 控制台与大屏
firmware/           ESP32 参考固件及执行器模拟
deploy/             Docker Compose 与 openEuler/systemd 部署
validation/         验证脚本与证据协议
bindings.ttl        协议绑定单一事实来源
thresholds.ttl      安全阈值配置
```

## 竞赛材料口径

软件实现、设计、测试与 PPT 的统一口径：

- **实现机制**：以代码和设计文档为准；
- **实测结果**：以《系统测试报告》为准；
- **竞赛展示**：不得把分析建议写成现场已执行；
- **合成数据**：不得当作采集精度或性能证据；
- **软件基线**：`master @ d45e5679d6cc6febc66c20e759b06375c2b6da20`。
