import json
import os
import unittest
from unittest.mock import patch
from backend.bedrock import generate_brief,TOOLS

class Client:
    def __init__(self,responses): self.responses=iter(responses)
    def converse(self,**kwargs): return {'output':{'message':{'role':'assistant','content':next(self.responses)}}}

def tool_calls():
    return [{'toolUse':{'toolUseId':str(i),'name':name,'input':{}}} for i,name in enumerate(TOOLS)]

class BedrockTests(unittest.TestCase):
    def run_brief(self,responses):
        with patch.dict(os.environ,{'BEDROCK_MODEL_ID':'mock-model'}),patch('boto3.client',return_value=Client(responses)):
            return generate_brief(0)
    def test_complete_tool_loop(self):
        result=self.run_brief([tool_calls(),[{'text':json.dumps({'summary':'Synthetic observations require review.','source_ids':['CAM-07','FIRMS-01','WX-01']})}]])
        self.assertEqual(result['tool_trace'],TOOLS)
        self.assertEqual(result['engine'],'Bedrock · mock-model')
    def test_no_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError,'required evidence'):
            self.run_brief([[{'text':'{"summary":"Unsupported","source_ids":["CAM-07"]}'}]])
    def test_unknown_source_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid brief'):
            self.run_brief([tool_calls(),[{'text':'{"summary":"Unsupported","source_ids":["INVENTED"]}'}]])
    def test_unknown_tool_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsupported model tool'):
            self.run_brief([[{'toolUse':{'toolUseId':'x','name':'send_alert','input':{}}}]])

if __name__=='__main__': unittest.main()
