审查版本：仅基于 master 提交 2bc72f5。运行前请先读 START_HERE.md 和 docs/master-audit.md。

# XA-202606 智慧工厂安全监控平台

浙江师范大学 · 第十五届挑战杯 · 揭榜挂帅赛道

车间里的传感器来自不同厂家，有的说 Modbus，有的发 MQTT，有的开 OPC UA，有的直接
POST JSON。这个平台把它们接到一起，校验数据，存成 RDF 知识图谱，在网页上展示。

真正的重点不是网页，是接新设备的方式。

## 核心做法

设备的参数写成本体三元组，放在根目录的 `bindings.ttl` 里。寄存器地址、缩放系数、
字节序、Modbus 功能码、轮询周期、OPC UA 节点号，全部写在那一个文件。平台读这个
文件，自动生成四种协议的适配代码。

实时 Modbus、OPC UA 和 MQTT 适配器从同一份已校验绑定表构造读取/订阅计划；设备 ID、
地址、单位、缩放、功能码、Topic 和节点号不再散落在协议代码里。生成物可用
`make check-generated` 校验，地址重叠和重复绑定会在加载阶段被拒绝。

接入一个**已有测量和单位类型**的新设备，只需修改 `bindings.ttl` 并重新生成；openEuler
部署可用 `sudo xa202606-reload` 让后端、绑定服务和活动适配器在原进程内重载配置，无需
重启进程。增加全新的测量或单位类型仍需同步修改 Python 消息契约、语义映射、本体和
测试，不能只增加 Turtle 三元组。

## 需要什么

- Python 3.11 以上
- Node.js 20 以上
- Apache Jena Fuseki（可以不装，装了才有知识图谱和 SPARQL 查询）
- Mosquitto（只有走 MQTT 的设备需要）

## 装

```bash
git clone https://github.com/sensoumi4946-cpu/xa202606-smart-factory.git
cd xa202606-smart-factory

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux

pip install -e shared -e backend -e connectivity -e analytics -e semantic-layer

cd dashboard && npm install && cd ..
```

## 环境变量

后端只有一个必须设：

```
API_KEY=你自己的密钥
```

远程控制还必须设置 `COMMAND_SIGNING_KEY`，设备端使用相同密钥。其余参数有本地开发
默认值。Fuseki 写入地址默认
`http://localhost:3030/factory/data`，查询地址 `http://localhost:3030/factory/query`。
设置 `SEMANTIC_WRITE_ENABLED=true` 才会启动知识图谱写入和同步任务。

前端打开后输入访问密钥。不要把密钥写进前端代码。详细步骤见 `START_HERE.md`。

## 跑起来

三个终端。

**后端**，必须在仓库根目录启动，不然找不到 `bindings.ttl`：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

启动日志里应该有 `loaded 17 protocol bindings`。如果是 0，说明路径不对。

**Fuseki**（可选）：

```bash
cd apache-jena-fuseki-5.2.0
./fuseki-server --update --mem /factory
```

**前端**：

```bash
cd dashboard
npm run dev
```

打开 http://localhost:5173

Docker Compose 默认启动后端、Fuseki、MQTT、REST 和执行器模拟器。连接真实 Modbus /
OPC UA 设备时使用硬件 profile，并按现场地址覆盖环境变量：

```bash
docker compose -f deploy/docker-compose.yml --profile hardware up -d --build
```

## 发一条数据试试

```bash
curl -X POST http://localhost:8000/ingest/api/v1/data \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 你的密钥" \
  -d '{"schema_version":"v1","device_id":"esp32_05_dht22","subsystem":"temp_humidity","protocol":"mqtt","measurements":[{"type":"temperature","value":26.1,"unit":"celsius"},{"type":"humidity","value":56.2,"unit":"percent"}]}'
```

返回里 `device_id` 会是 `ESP32_001`，`reported_device_id` 是你发的那个名字。这是
本体里的别名在起作用——同一块板子用不同协议上报会用不同名字，平台自己认成一台设备。

设备如果只能出裸寄存器、发不了 JSON，就挂到对应的协议适配器上，适配器会按本体里的
地址和缩放系数去解，固件那边不用改。

## 改了 bindings.ttl 之后

```bash
python scripts/generate_adapters.py
```

生成的四个 `generated_*_adapter.py` 是提交进仓库的，跟本体不一致时测试会报错。

## 测试

```bash
python -m pytest backend/tests connectivity/tests semantic-layer/tests analytics/tests shared/tests benchmark/tests validation/tests -q
cd firmware && python -m pytest tests -q && cd ..
cd dashboard && npm test -- --run && npm run build && cd ..
python scripts/generate_adapters.py --check
python scripts/validate_sample_data.py
```

## openEuler 部署

唯一支持的国产操作系统部署目标是 **openEuler 24.03 LTS**（x86_64 / AArch64）。
使用 systemd 原生部署，不要求购买 UOS 或麒麟：

```bash
sudo bash deploy/openeuler/install.sh
sudoedit /etc/xa202606/backend.env
sudoedit /etc/xa202606/connectivity.env
sudo bash deploy/openeuler/verify.sh
```

详细步骤、离线 wheelhouse 和 OPC UA 证书配置见 `deploy/openeuler/README.md`。
修改绑定或阈值后运行 `sudo xa202606-reload`；它会先校验再执行无进程重启的协调重载。
提交材料中的原创性/保密性声明核对稿见
`docs/originality-confidentiality-declaration-template.md`；必须用组委会正式表格签署，
仓库模板不能替代正式文件。

## 五条示例数据的性质

`data/samples/five_subsystems.jsonl` 是经过消息契约、SHACL 和协议绑定三重校验的
**合成演示夹具**，不是传感器实测原始数据。运行 `python scripts/seed_sample_data.py
--dry-run` 可以复核。实测精度、性能和稳定性必须按 `validation/EVIDENCE_PROTOCOL.md`
采集，不能用这五个手填数值代替。

三类配置校验用例：

```bash
python validation/run_validation.py
```

合法地址通过并生成代码，非法地址和类型不一致在加载阶段被拒绝，都在 100ms 以内。

可复现的已知类型设备接入检查：

```bash
python validation/run_benchmark.py
```

## 目录

```
firmware/          ESP32 固件
connectivity/      四个协议适配器，运行计划由 bindings.ttl 构造
backend/           FastAPI，接入、校验、存储
semantic-layer/    本体解析、SHACL 校验、代码生成、RDF 映射
analytics/         阈值规则、趋势预测
dashboard/         Vue 3 前端
validation/        配置校验用例和对比脚本
bindings.ttl       设备参数，唯一事实来源
```

## 现在的硬件

| 板子 | 传感器 | 子系统 | 协议 |
|---|---|---|---|
| ESP32_001 | DHT22 | 温湿度 | Modbus / MQTT / OPC UA（绑定已定义） |
| ESP32_002 | 红外对射 | 货物计数 | REST |
| ESP32_003 | PIR + 继电器 | 照明 | REST |
| ESP32_004 | HC-SR04 | AGV 避障 | OPC UA |
| ESP32_005 | MQ-2 / MQ-7 | 危险气体 | Modbus |

上表描述的是绑定拓扑，不等同于硬件完成状态。五块板已有参考采集固件，其中
ESP32_004 通过 openEuler 串口网关暴露 OPC UA 节点；所有草图仍需在实际板卡上编译、
接线、校准和留存端到端证据。

## 还没做完的

- 报文里没有设备自己的时间戳，用的是服务器收到的时间。断网重连后一批数据会挤在
  同一时刻。
- 固件版本号和 MAC 尚未统一上报；部分参考固件只把运行时长放在 `raw_payload`。
- 没跑过完整的硬件端到端测试；已有 openEuler 安装和自检脚本，但尚无目标机执行日志。
- 接入延迟、采集精度、跨平台通信效率、CPU、内存和连续运行稳定性还没测。
- OPC UA 适配器支持 Basic256Sha256、SignAndEncrypt、客户端证书和服务端证书固定；
  现场仍必须签发证书并按 `deploy/openeuler/connectivity.env.example` 配置，未配置时不能
  作为生产安全链路使用。

## 常见问题

**启动日志说 bindings file not found**

不在仓库根目录启动的。`cd` 到根目录再跑 uvicorn。

**返回 kg_write: queued**

写入在后台执行。检查 `SEMANTIC_WRITE_ENABLED`、Fuseki 健康状态和后端日志确认结果。

**界面一直显示未检测到设备**

先 `curl /api/v1/latest` 看后端有没有数据。有数据但界面空的，多半是
`dashboard/.env` 没配，或者配了但没重启 `npm run dev`。

**数据库删了还是能看到旧设备**

数据库在仓库根目录的 `data/smart_factory.db`，不是 `backend/data/`。
