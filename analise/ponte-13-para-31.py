# -*- coding: utf-8 -*-
"""De onde veio a diferença entre a caixa de R$ 13,39 e a de R$ 31,16."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"

print("="*88); print("A CAIXA DE R$ 13,39 — ESSENCIAL, 5 ITENS"); print("="*88)
ESS=[("Pão de fermentação natural","200 g",3.20),("Manteiga em tablete","20 g",0.92),
     ("Geleia artesanal envasada","60 g",1.68),("Fruta da estação","250 g",1.25),
     ("Café em grão","36 g",1.80)]
for d,q,c in ESS: print(f"  {d:<40}{q:>10}{brl(c):>10}")
i0=sum(c for _,_,c in ESS)
print(f"  {'':<40}{'insumo':>10}{brl(i0):>10}")
print(f"  {'':<40}{'embalagem':>10}{brl(4.15):>10}   (2 copos de papel descartáveis)")
print(f"  {'':<40}{'CUSTO':>10}{brl((i0+4.15)*1.03):>10}")

print("\n"+"="*88); print("O QUE VOCÊ ADICIONOU"); print("="*88)
ADD=[("2 mini croissants",4.00),("2 ovos cozidos",1.80),("Queijo colonial 60 g",2.16),
     ("Peito de peru 60 g",1.92),("Pesto no potinho",2.05),("Meio avocado",2.70),
     ("2 mini cookies",2.40)]
a=0
for d,c in ADD: print(f"  {d:<52}{brl(c):>10}"); a+=c
print(f"  {'':<52}{brl(a):>10}   pedido seu")
MEU=[("Iogurte natural com mel",1.80),("Granola da casa",0.60),
     ("Sal e pimenta em sachê",0.10),("Cartão com o nome",0.20)]
b=0
for d,c in MEU: print(f"  {d:<52}{brl(c):>10}"); b+=c
print(f"  {'':<52}{brl(b):>10}   sugestão minha")
print(f"  {'TOTAL ADICIONADO':<52}{brl(a+b):>10}")

print("\n"+"="*88); print("O QUE DIMINUIU"); print("="*88)
SUB=[("Pão: 200 g → 2 fatias de 60 g",-1.28),("Fruta: 250 g → 200 g",-0.25),
     ("Geleia: envasada 60 g → mini-pote pronto de 25 g",-0.48),
     ("Embalagem: 2 copos de papel → térmica de comodato",-0.47)]
s=0
for d,c in SUB: print(f"  {d:<52}{brl(c):>10}"); s+=c
print(f"  {'':<52}{brl(s):>10}")

print("\n"+"="*88); print("A PONTE"); print("="*88)
print(f"  {'Caixa Essencial':<40}{brl(13.39):>12}")
print(f"  {'+ o que você pediu':<40}{brl(a):>12}")
print(f"  {'+ o que eu sugeri':<40}{brl(b):>12}")
print(f"  {'− o que diminuiu':<40}{brl(s):>12}")
print(f"  {'+ 3% de quebra sobre a diferença':<40}{brl((a+b+s)*0.03):>12}")
print(f"  {'= Caixa completa':<40}{brl(31.16):>12}")
print(f"\n  Nenhum preço mudou. O que mudou foi o CONTEÚDO: de 5 itens para 16.")
print(f"  A embalagem até caiu — de {brl(4.15)} para {brl(3.68)}, porque a térmica")
print(f"  em comodato substituiu os dois copos descartáveis.")

print("\n"+"="*88); print("QUAL DAS DUAS DÁ MAIS DINHEIRO"); print("="*88)
ENT=2.50; COM=.15
def conta(nome,custo,preco):
    s=preco-custo-ENT-preco*COM
    return nome,preco,custo,s,s/preco
L=[conta("Essencial",13.39,59),conta("Essencial",13.39,69),
   conta("Completa",31.16,99),conta("Completa",31.16,109)]
print(f"  {'Caixa':<12}{'Preço':>8}{'Custo':>10}{'CMV':>7}{'Sobra':>10}{'Margem':>9}")
for n,p,c,s,m in L:
    print(f"  {n:<12}{brl(p,0):>8}{brl(c):>10}{pc(c/p):>7}{brl(s):>10}{pc(m):>9}")
e=42.76; co=50.49
print(f"\n  A Completa a R$ 99 sobra {brl(co)}. A Essencial a R$ 69 sobra {brl(e)}.")
print(f"  A Completa ganha por {brl(co-e)} — só {pc(co/e-1)} a mais.")
print(f"\n  Mas a Essencial custa 30% menos para o hóspede. Se ela converter")
print(f"  {pc(co/e-1)} melhor por ser mais barata, as duas empatam no bolso.")
print(f"  Isso não é motivo para escolher uma — é motivo para vender AS DUAS:")
print(f"    · a Completa a R$ 99 faz a Essencial a R$ 69 parecer barata")
print(f"    · quem ia gastar R$ 69 às vezes sobe para R$ 99 vendo a lista")
print(f"    · e as duas usam a mesma caixa, a mesma moto e o mesmo minuto de montagem")
