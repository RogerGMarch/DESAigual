import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=Path('web/public/data'); m={f['properties']['id']:f['properties'] for f in json.loads((p/'municipalities.geojson').read_text())['features']}
fig,ax=plt.subplots(figsize=(11,4.9),dpi=180)
fig.patch.set_facecolor('#ffffff'); ax.set_facecolor('#ffffff')
fig.text(.055,.92,'Dos ciudades de León. Dos accesos distintos.',fontsize=23,fontweight='normal',color='#252525')
fig.text(.055,.855,'Población estimada con acceso a un DESA a pie, según el umbral de tiempo',fontsize=12,color='#666666')
for y,key,name in [(1,'24089','León'),(0,'24115','Ponferrada')]:
 d=m[key]; a,b=d['coverage5'],d['coverage15']
 ax.plot([a,b],[y,y],color='#cdd5d1',lw=5,zorder=2)
 ax.scatter([a],[y],color='#418b80',s=100,zorder=3)
 ax.scatter([b],[y],color='#b34f40',s=100,zorder=3)
 ax.text(-4,y,name,ha='right',va='center',fontsize=14,color='#252525')
 ax.text(a,y+.2,f'{a:.1f}%'.replace('.',','),ha='center',fontsize=13,color='#32695f')
 ax.text(b,y+.2,f'{b:.1f}%'.replace('.',','),ha='center',fontsize=13,color='#a04a3e')
ax.set_xlim(0,105);ax.set_ylim(-.45,1.55)
ax.set_yticks([]); ax.set_xticks([0,25,50,75,100],['0%','25%','50%','75%','100%'])
ax.tick_params(axis='x',colors='#888888',length=0,labelsize=10)
ax.grid(axis='x',color='#ededed',lw=.7,zorder=0)
for spine in ax.spines.values():spine.set_visible(False)
fig.text(.205,.195,'● Hasta 5 minutos',fontsize=11,color='#418b80')
fig.text(.445,.195,'● Menos de 15 minutos',fontsize=11,color='#b34f40')
fig.text(.055,.095,'Estimaciones del prototipo: población municipal distribuida entre edificios residenciales del Catastro.',fontsize=10,color='#777777')
fig.text(.055,.055,'Fuente: exportación actual del análisis. No son tiempos observados ni de respuesta sanitaria.',fontsize=10,color='#777777')
fig.subplots_adjust(left=.205,right=.955,bottom=.29,top=.77)
fig.savefig('web/editorial/city-comparison.png',facecolor='white')
