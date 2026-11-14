import test from 'node:test';
import assert from 'node:assert/strict';
import {checkRoutes,intersects,createDraft} from '../dist/core.js';
test('initial and expanded hazard exclude Ridge Road but retain Canyon Connector',()=>{for(const stage of [0,1])assert.deepEqual(checkRoutes(stage).map(r=>r.blocked),[true,false]);});
test('closure excludes both candidates and draft withholds route instructions',()=>{assert.ok(checkRoutes(2).every(r=>r.blocked));const d=createDraft(2);assert.equal(d.route_id,null);assert.match(d.text,/Route instructions are withheld/);assert.equal(d.approved,false);});
test('geometry includes tangent and zero-length segments',()=>{assert.equal(intersects([0,1],[4,1],{x:2,y:0,r:1}),true);assert.equal(intersects([0,0],[0,0],{x:0,y:0,r:1}),true);assert.equal(intersects([0,0],[0,0],{x:2,y:2,r:1}),false);});
test('drafts are exercises and never claim a safe route',()=>{const d=createDraft(0);assert.equal(d.route_id,'B');assert.ok(d.text.startsWith('EXERCISE ONLY'));assert.match(d.text,/unverified/);assert.doesNotMatch(d.text,/safest|safe route/i);});
