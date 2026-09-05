# -*- coding: utf-8 -*-
"""Ficha técnica dos itens de preço fixo do cardápio moka. Atacado R$/kg."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
P={"acai":17.50,"acai14":24.00,"banana":6,"morango":28,"granola":20,"ninho":48,"mel":30,
   "cacau_calda":25,"amendoim":35,"nibs":70,"frutas":16,"castanha":75,"coco":40,
   "creme_pistache":95,"pistache":140,"damasco":60,"leite_cond":19,"nutella":65,
   "sorvete":22,"choc_po":30,"marshmallow":38,"avela":110,"cookie":35,"chantilly":25,
   "doce_leite":24,"frutas_verm":32,"oreo":45}
EMB_BOWL=1.10; EMB_COPO=1.60; QUEBRA=.025

def ficha(nome,preco,itens,emb=EMB_BOWL):
    c=sum(P[k]*g/1000 for k,g in itens)+emb
    c*= 1+QUEBRA
    return (nome,preco,c,c/preco)

L=[
 ficha("Bowl Ferrugem",32,[("acai",250),("morango",60),("banana",50),("granola",30),("ninho",15),("mel",10)]),
 ficha("Bowl Moka",34,[("acai",250),("cacau_calda",25),("banana",50),("amendoim",35),("nibs",15),("granola",30)]),
 ficha("Bowl Amazônia",34,[("acai14",250),("frutas",70),("banana",50),("castanha",25),("mel",10)]),
 ficha("Bowl Pistache",36,[("acai",250),("creme_pistache",40),("damasco",30),("banana",50),("pistache",20),("granola",30)]),
 ficha("Copo Moka Red",28,[("acai",280),("frutas_verm",60),("banana",50),("granola",35),("ninho",15)],EMB_COPO),
 ficha("Copo Moka Pistache",30,[("acai",280),("creme_pistache",45),("banana",50),("damasco",30),("granola",35)],EMB_COPO),
 ficha("Milkshake Cookie&Cream",26,[("sorvete",200),("oreo",35),("cacau_calda",25),("chantilly",20)],EMB_COPO),
 ficha("Milkshake Morango Real",26,[("sorvete",200),("morango",70),("chantilly",25)],EMB_COPO),
 ficha("Milkshake Moka Cacau",26,[("sorvete",200),("choc_po",20),("nibs",10),("chantilly",20)],EMB_COPO),
 ficha("Caneca Morango Love",20,[("choc_po",25),("sorvete",90),("frutas_verm",45),("marshmallow",35)],EMB_COPO),
 ficha("Caneca Moka Dream",20,[("choc_po",25),("sorvete",90),("avela",30),("castanha",25),("marshmallow",35)],EMB_COPO),
 ficha("Caneca Doce de Leite",20,[("choc_po",25),("sorvete",90),("doce_leite",45),("cookie",20),("marshmallow",35)],EMB_COPO),
]
print("="*76); print("ITENS DE PREÇO FIXO — CMV"); print("="*76)
print(f"  {'Item':<26}{'Venda':>9}{'Custo':>10}{'CMV':>8}{'Sobra':>10}")
for n,p,c,cmv in sorted(L,key=lambda x:-x[3]):
    flag=" ⚠" if cmv>.35 else ""
    print(f"  {n:<26}{brl(p,0):>9}{brl(c):>10}{cmv*100:>7.1f}%{brl(p-c):>10}{flag}")

print("\n  Referência · self-service 415 g a R$ 74,90/kg = R$ 31,08, custo R$ 8,13 = 26,2%")

print("\n"+"="*76); print("BUFFET A R$ 74,90/kg — O QUE CADA TOPPING DEVOLVE"); print("="*76)
for k,v in sorted(P.items(),key=lambda x:-x[1])[:10]:
    print(f"  {k:<18}{brl(v,0):>9}/kg   CMV {v/74.90*100:>5.1f}%{'  ⚠ no acesso livre destrói a margem' if v/74.90>.6 else ''}")
