import { test } from 'node:test';
import assert from 'node:assert/strict';
import { upstreamValue } from '../src/lib/upstreamDisplay.ts';
test('nested resume items remain readable without object coercion', () => {
 const result = upstreamValue({company:'示例公司',bullets:['完成交付',{text:'提高效率'}]});
 assert.match(result,/公司：示例公司/); assert.match(result,/完成交付/); assert.match(result,/提高效率/); assert.doesNotMatch(result,/\[object Object\]/);
});
test('missing and empty values remain distinguishable',()=>{
 assert.equal(upstreamValue(null),'（无）'); assert.equal(upstreamValue([]),'（空列表）'); assert.equal(upstreamValue(''),'（空）');
});
