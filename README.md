# XA-202606 智慧工厂安全监控平台

浙江师范大学 · 第十五届挑战杯 · 揭榜挂帅赛道

车间里的传感器来自不同厂家，有的说 Modbus，有的发 MQTT，有的开 OPC UA，有的直接
POST JSON。这个平台把它们接到一起，校验数据，存成 RDF 知识图谱，在网页上展示。

真正的重点不是网页，是接新设备的方式。

## 核心做法

设备的参数写成本体三元组，放在根目录的 `bindings.ttl` 里。寄存器地址、缩放系数、
字节序、Modbus 功能码、轮询周期、OPC UA 节点号，全部写在那一个文件。平台读这个
文件，自动生成四种协议的适配代码。

Python 里没有任何一处写死的寄存器地址。有测试专门检查这件事，谁往适配器里写了
地址，测试就会失败。

接一台新设备：写几行三元组，重新生成，完事。不改业务代码，不重启服务。

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

其余的都有默认值，本机跑不用改。Fuseki 写入地址默认
`http://localhost:3030/factory/data`，查询地址 `http://localhost:3030/factory/query`。

前端在 `dashboard/.env` 里写：

```
VITE_API_BASE_URL=http://localhost:8000/
VITE_API_KEY=跟上面一样的密钥
```

Vite 只在启动时读 `.env`，改了要重启 `npm run dev`。

## 跑起来

三个终端。

**后端**，必须在仓库根目录启动，不然找不到 `bindings.ttl`：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

启动日志里应该有 `loaded 13 protocol bindings`。如果是 0，说明路径不对。

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

Windows 上用 `scripts\generate_adapters.ps1`。

生成的四个 `generated_*_adapter.py` 是提交进仓库的，跟本体不一致时测试会报错。

## 测试

```bash
cd semantic-layer && python -m pytest tests -q && cd ..
cd connectivity  && python -m pytest tests -q && cd ..
cd backend       && python -m pytest tests -q && cd ..
cd analytics     && python -m pytest tests -q && cd ..
cd dashboard     && npx vitest run && cd ..
```

三类配置校验用例：

```bash
python validation/run_validation.py
```

合法地址通过并生成代码，非法地址和类型不一致在加载阶段被拒绝，都在 100ms 以内。

人工配置对比：

```bash
python validation/run_benchmark.py
```

## 目录

```
firmware/          ESP32 固件
connectivity/      四个协议适配器，不含任何绑定常量
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
| ESP32_001 | DHT22 | 温湿度 | Modbus / MQTT / OPC UA |
| ESP32_002 | 红外对射 | 货物计数 | REST |
| ESP32_003 | PIR + 继电器 | 照明 | REST |
| ESP32_004 | HC-SR04 | AGV 避障 | OPC UA |

气体和 AGV 子系统在本体里声明了但还没接硬件。这是故意留着的——硬件到了以后接
进来不需要写代码。

## 还没做完的

- 报文里没有设备自己的时间戳，用的是服务器收到的时间。断网重连后一批数据会挤在
  同一时刻。
- 仓库里只有 ESP32_001 的固件，另外三块板子的还没提交。
- 固件版本号、MAC、运行时长、报文数固件没上报，界面上这几列是空的。
- 没跑过完整的硬件端到端测试。
- 接入延迟、CPU、内存、连续运行稳定性还没测。

## 常见问题

**启动日志说 bindings file not found**

不在仓库根目录启动的。`cd` 到根目录再跑 uvicorn。

**返回 kg_written: False**

Fuseki 没起，或者 `FUSEKI_ENDPOINT` 被环境变量覆盖成了错的地址。清掉环境变量，
用默认值。

**界面一直显示未检测到设备**

先 `curl /api/v1/latest` 看后端有没有数据。有数据但界面空的，多半是
`dashboard/.env` 没配，或者配了但没重启 `npm run dev`。

**数据库删了还是能看到旧设备**

数据库在仓库根目录的 `data/smart_factory.db`，不是 `backend/data/`。
