import asyncio, json, os, secrets, socket, subprocess, tempfile, time, sys
from pathlib import Path
import httpx
from amqtt.broker import Broker
import paho.mqtt.publish as publish

ROOT=Path(__file__).resolve().parents[1]
PYTHON=sys.executable
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]

async def main():
    broker_port, api_port=port(),port()
    work=Path(tempfile.mkdtemp(prefix='factory-live-'))
    key=secrets.token_hex(32)
    env=os.environ|{'API_KEY':key,'COMMAND_SIGNING_KEY':secrets.token_hex(32),'HARDWARE_PROFILE':'real','DATABASE_PATH':str(work/'data.db'),'PROVENANCE_AUDIT_DB':str(work/'prov.db'),'SEMANTIC_WRITE_ENABLED':'false','MQTT_BROKER_HOST':'127.0.0.1','MQTT_BROKER_PORT':str(broker_port),'BACKEND_URL':f'http://127.0.0.1:{api_port}','PUBLIC_BACKEND_URL':f'http://127.0.0.1:{api_port}'}
    broker=Broker({'listeners':{'default':{'type':'tcp','bind':f'127.0.0.1:{broker_port}'}},'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
    await broker.start()
    log=open(work/'runtime.log','w')
    processes=[]
    try:
        backend=subprocess.Popen([PYTHON,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(api_port)],cwd=ROOT,env=env,stdout=log,stderr=log);processes.append(backend)
        async with httpx.AsyncClient(base_url=env['BACKEND_URL'],headers={'X-API-Key':key},trust_env=False) as client:
            for _ in range(100):
                try:
                    if (await client.get('/health')).status_code==200:break
                except httpx.HTTPError:pass
                await asyncio.sleep(.1)
            else:raise RuntimeError('backend failed to start')
            unauth=(await client.get('/api/v1/devices',headers={'X-API-Key':''})).status_code
            assert unauth==401
            adapter=subprocess.Popen([PYTHON,'-m','connectivity.runner','--adapter','mqtt'],cwd=ROOT,env=env,stdout=log,stderr=log);processes.append(adapter)
            await asyncio.sleep(1)
            sample=json.loads((ROOT/'data/samples/five_subsystems.jsonl').read_text().splitlines()[0])
            await asyncio.to_thread(publish.single,'factory/temp_humidity/sensors/ESP32_001/reading',json.dumps(sample),hostname='127.0.0.1',port=broker_port,qos=1)
            latest=[]
            for _ in range(50):
                latest=(await client.get('/api/v1/latest')).json()
                if latest:break
                await asyncio.sleep(.1)
            assert latest and {m['type'] for m in latest[0]['measurements']}=={'temperature','humidity'},latest
            results=[]
            for line in (ROOT/'data/samples/supplied_hardware_samples.jsonl').read_text().splitlines():
                response=await client.post('/ingest/api/v1/data',json=json.loads(line));results.append(response.status_code)
            assert all(code==200 for code in results),results
            firmware_sample=sample|{'measurements':sample['measurements']+[{'type':p,'unit':'status','value':0} for p in ['device_status','error_code','sensor_status']]}
            response=await client.post('/ingest/api/v1/data',json=firmware_sample)
            assert response.status_code==200,response.text
            command=await client.post('/api/v1/control',json={'device_id':'ESP32_001','subsystem':'temp_humidity','action':'off'})
            assert command.status_code==202 and command.json()['dispatched']
            report={'classification':'local software integration, no physical sensors','master_commit':'2bc72f57e18fd8a835d822c6d03ffa571c8109b5','unauthenticated_status':unauth,'mqtt_full_envelope_to_sqlite':True,'supplied_examples_accepted':len(results),'firmware_status_envelope_accepted':True,'signed_command_published':True,'hardware_execution_verified':False,'hardware_48_hour_test_performed':False}
            (ROOT/'validation/audit_live_result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:
        for process in reversed(processes):process.terminate()
        for process in processes:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill()
        log.close();await broker.shutdown()

asyncio.run(main())
