import { test } from 'node:test';
import assert from 'node:assert/strict';
import { contentDiff, applyChoices } from '../src/lib/contentDiff.ts';
test('leaf decisions retain rejected text and apply accepted nested changes', () => {
 const before={version:2,summary:'mine',experience:[{title:'old',detail:'keep'}]};
 const after={version:99,summary:'AI',experience:[{title:'new',detail:'keep'}]};
 const diffs=contentDiff(before,after);
 assert.equal(diffs.length,2);
 const selected=new Set(diffs.filter(d=>d.path.at(-1)==='title').map(d=>d.id));
 assert.deepEqual(applyChoices(before,diffs,selected),{version:2,summary:'mine',experience:[{title:'new',detail:'keep'}]});
});
test('multiple removed array items do not shift selected paths',()=>{
 const before={skills:['a','b','c','d']}; const diffs=contentDiff(before,{skills:['a']});
 assert.deepEqual(applyChoices(before,diffs,new Set(diffs.map(d=>d.id))),{skills:['a']});
});
test('LLM prototype keys are not applied',()=>{
 const diffs=contentDiff({},JSON.parse('{"__proto__":{"polluted":true},"constructor":{"x":1},"summary":"ok"}'));
 assert.equal(diffs.length,1); assert.deepEqual(applyChoices({},diffs,new Set(diffs.map(d=>d.id))),{summary:'ok'});
});
test('rejecting an earlier new array item must not leave holes',()=>{
 const base={skills:['A']}; const changes=contentDiff(base,{skills:['A','B','C','D']});
 assert.deepEqual(applyChoices(base,changes,new Set(changes.filter(c=>c.after!=='B').map(c=>c.id))),{skills:['A','C','D']});
});
