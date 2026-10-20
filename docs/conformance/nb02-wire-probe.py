"""Locked upstream SDK wire capture. Fake clients/keys; model network forbidden."""
import asyncio
import importlib.metadata
import importlib.util
import json
import pathlib
import socket
import sys
from types import SimpleNamespace

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
# Windows creates a local event-loop wakeup pair before any model network guard.
loop=asyncio.new_event_loop()
source=ROOT/'docs/conformance/noveltybench-request-conformance.py'
spec=importlib.util.spec_from_file_location('reference_probe',source)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
import httpx
import httpx2
import openai
import anthropic

bodies=[]

def openai_response(request):
 body=json.loads(request.content)
 assert str(request.url)=='https://api.openai.com/v1/chat/completions'
 assert 'max_completion_tokens' not in body and 'service_tier' not in body
 bodies.append({'provider':'openai','path':request.url.path,'body':body})
 text=json.dumps({'groups':[[0,1],[2]]})
 return httpx.Response(200,json={'id':'chatcmpl-fixture','object':'chat.completion','created':0,'model':body['model'],'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':text}}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}},headers={'x-request-id':'fixture-openai'},request=request)

def anthropic_response(request):
 body=json.loads(request.content)
 assert str(request.url)=='https://api.anthropic.com/v1/messages'
 assert body['max_tokens']==16000 and 'service_tier' not in body
 bodies.append({'provider':'anthropic','path':request.url.path,'body':body})
 return httpx2.Response(200,json={'id':'msg-fixture','type':'message','role':'assistant','content':[{'type':'text','text':'{"score":7}'}],'model':body['model'],'stop_reason':'end_turn','stop_sequence':None,'usage':{'input_tokens':10,'output_tokens':5}},headers={'request-id':'fixture-anthropic'},request=request)

async def main():
 ns,seals=probe.upstream()
 async with openai.AsyncOpenAI(api_key='offline-fixture',base_url='https://api.openai.com/v1',http_client=httpx.AsyncClient(transport=httpx.MockTransport(openai_response),trust_env=False)) as oclient:
  async with anthropic.AsyncAnthropic(api_key='offline-fixture',base_url='https://api.anthropic.com',http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(anthropic_response),trust_env=False)) as aclient:
   ns['anthropic']=SimpleNamespace(AsyncAnthropic=lambda:aclient)
   ns['oai_client']=lambda:oclient
   probe.extract('judge.py',{'judge_client'},ns)
   partition_call=ns['Call'](ns['JUDGE_SYSTEM'],'three full responses',ns['Partition'])
   score_call=ns['Call'](ns['SCORE_SYSTEM'],'one full response',ns['Score'])
   partition=await ns['judge']('gpt-5.6-luna',partition_call)
   score=await ns['judge']('claude-opus-5',score_call)
   assert partition.groups==[[0,1],[2]] and score.score==7
 result={'format':'buddha.review.nb02-locked-sdk-wire.v1','commit':probe.COMMIT,'models':{'partition':'gpt-5.6-luna','quality':'claude-opus-5'},'sdk_versions':{n:importlib.metadata.version(n) for n in ['openai','anthropic','pydantic','numpy','pandas','httpx','httpx2']},'upstream_source_seals':seals,'source_execution':'unchanged selected official judge plus its judge_client function; real locked SDK serialization and parsing; fake in-memory HTTP transports','provider_network_calls':0,'actual_api_keys_used':False,'captured_bodies':bodies,'parsed_partition':partition.model_dump(),'parsed_score':score.model_dump()}
 (ROOT/'runs/reviews/nb02-locked-wire.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'versions':result['sdk_versions'],'body_keys':{r['provider']:list(r['body']) for r in bodies},'provider_network_calls':0}))

try:
 loop.run_until_complete(main())
finally:
 loop.close()
