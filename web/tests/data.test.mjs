import test from "node:test";
import assert from "node:assert/strict";
import { searchMunicipalities, rankCandidates } from "../src/data.js";

function town(
  id,
  name,
  population,
  coverage15,
  coordinates = [0, 0],
  status = "available",
) {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates },
    properties: { id, name, population, coverage15, status },
  };
}
test("an exact city name wins over an earlier substring match", () => {
  const towns = [
    town("37117", "DOÑINOS DE SALAMANCA", 2000, 20),
    town("37274", "SALAMANCA", 140000, 98),
  ];
  assert.equal(
    searchMunicipalities(towns, "Salamanca")[0].properties.id,
    "37274",
  );
  assert.equal(
    searchMunicipalities([town("24089", "LEÓN", 123000, 98)], " leon ")[0]
      .properties.id,
    "24089",
  );
  assert.deepEqual(searchMunicipalities(towns, "no-such-town"), []);
});
test("different objectives change the order and exclude unknown municipalities", () => {
  const municipalities = {
    features: [
      town("1", "Large", 10000, 50),
      town("2", "Small", 100, 0),
      town("3", "Unknown", 100000, 0, [1, 1], "missing"),
    ],
  };
  const aeds = {
    features: [town("a", "", 0, 0, [0, 0]), town("b", "", 0, 0, [1, 1])],
  };
  const ranked = rankCandidates(municipalities, aeds);
  assert.equal(ranked.population[0].properties.id, "1");
  assert.equal(ranked.equity[0].properties.id, "2");
  for (const list of Object.values(ranked)) assert.equal(list.length, 2);
});
test("duplicate device coordinates do not count as a second distinct location", () => {
  const municipalities = {
    features: [
      town("1", "A", 100, 0, [0, 0]),
      town("2", "B", 100, 0, [0.3, 0]),
    ],
  };
  const sites = [town("a", "", 0, 0, [0, 0]), town("b", "", 0, 0, [1, 0])];
  const a = rankCandidates(municipalities, { features: sites });
  const b = rankCandidates(municipalities, {
    features: [...sites, ...sites, ...sites],
  });
  assert.deepEqual(
    a.spatial.map((f) => f.properties.id),
    b.spatial.map((f) => f.properties.id),
  );
});

import { populationGroups } from '../src/data.js';
test('population chart retains all municipalities and respects size boundaries', () => {
  const features=[99,100,499,500,50000].map((population,i)=>({properties:{id:String(i),population,status:'missing'}}));
  const groups=populationGroups(features);
  assert.deepEqual(groups.map(g=>g.count),[1,2,1,0,0,1]);
  assert.equal(groups.reduce((s,g)=>s+g.towns,0),100);
  assert.ok(Math.abs(groups.reduce((s,g)=>s+g.people,0)-100)<1e-9);
});

import { accessPopulationGroups } from '../src/data.js';
test('population outside the threshold excludes missing and review results',()=>{
 const features=[{population:100,status:'available',coverage15:25},{population:200,status:'missing'},{population:300,status:'review'},{population:10000,status:'available',coverage15:100}].map(properties=>({properties}));
 const groups=accessPopulationGroups(features);
 assert.equal(groups[0].covered,25);assert.equal(groups[0].outside,75);assert.equal(groups[0].unknown,500);
 assert.equal(groups.reduce((sum,g)=>sum+g.covered+g.outside+g.unknown,0),10600);
});
