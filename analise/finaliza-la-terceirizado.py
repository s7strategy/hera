# -*- coding: utf-8 -*-
"""Formato 'chega pronto, finaliza lá': base e massa terceirizadas, máquina de
café alugada. O que se ganha em capex e folha, e onde a margem realmente vaza."""
def brl(v,c=0): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=1): return f"{v*100:.{c}f}%"
SM=1_621; CLT=SM*1.4

print("="*90); print("O QUE O FORMATO EVITA"); print("="*90)
EVITA=[("Forno de lastro ou turbo",14_000),("Masseira espiral",6_500),
       ("Câmara de fermentação controlada",9_000),("Bancada e utensílios de padaria",3_500),
       ("Máquina de espresso + moedor",12_000)]
for n,v in EVITA: print(f"  {n:<46}{brl(v):>11}")
CAPEX=sum(v for _,v in EVITA); PADEIRO=CLT*12
print(f"  {'CAPEX EVITADO':<46}{brl(CAPEX):>11}")
print(f"\n  {'Padeiro CLT o ano todo':<46}{brl(PADEIRO):>11}/ano")
print(f"  {'Aluguel da máquina de café · R$ 160/mês':<46}{brl(160*12):>11}/ano  (overhead)")
print(f"\n  Sai {brl(CAPEX)} de investimento e {brl(PADEIRO)}/ano de folha; entra {brl(160*12)}/ano.")
print(f"  A máquina de espresso era a última lacuna do investimento. Fechou.")

# ── ficha da linha, com louça de salão e não embalagem de delivery ───────────
P={"cafe":55,"leite":5,"pao":24,"massa":14,"croissant_un":3.80,"avocado":18,"ovo_un":0.90,
   "bacon":38,"microverde":120,"banana":6,"amendoim":35,"mel":30,"queijo":45,"bacon_jam":40,
   "bufala":60,"tomate":12,"pesto":60,"frango":28,"presunto_cru":90,"ricota":28,"rucula":25,
   "tomate_confit":25,"matcha":400,"calda":18,"pdq":32,"bolo":32,"cookie_un":2.80,"cha_un":0.80}
SALAO=0.30; COPO=1.20
def f(nome,preco,itens,emb=SALAO):
    c=sum((P[k]*g/1000 if isinstance(g,(int,float)) and k not in ("croissant_un","ovo_un","cookie_un","cha_un")
           else P[k]*g) for k,g in itens)+emb
    c*=1.025
    return (nome,preco,c,c/preco)

ITENS=[
 f("Espresso",6,[("cafe",18)],0.25),
 f("Cappuccino",10,[("cafe",18),("leite",150)]),
 f("Latte",10,[("cafe",18),("leite",200)]),
 f("Moka",12,[("cafe",18),("leite",200),("calda",25)]),
 f("Iced latte",12,[("cafe",18),("leite",150)],COPO),
 f("Iced moka",14,[("cafe",18),("leite",150),("calda",25)],COPO),
 f("Matcha latte",14,[("matcha",4),("leite",200)],0.40),
 f("Chá da casa",8,[("cha_un",1)],0.25),
 f("Moka toast",18,[("pao",90),("avocado",80),("ovo_un",1),("bacon",40),("microverde",10)],0.80),
 f("Banana toast",14,[("pao",90),("banana",60),("amendoim",35),("mel",15)]),
 f("Croissant Moka",18,[("croissant_un",1),("ovo_un",2),("queijo",40),("bacon_jam",30)]),
 f("Croissant Caprese",17,[("croissant_un",1),("bufala",50),("tomate",40),("pesto",20)]),
 f("Focaccia tomate & búfala",16,[("massa",150),("tomate_confit",50),("bufala",60)],0.70),
 f("Focaccia frango & avocado",17,[("massa",150),("frango",70),("avocado",50)],0.70),
 f("Focaccia presunto cru & ricota",18,[("massa",150),("presunto_cru",40),("ricota",50),("rucula",15)],0.70),
 f("Pão de queijo · 4 un",6,[("pdq",80)],0.25),
 f("Bolo de cenoura c/ chocolate",10,[("bolo",100)]),
 f("Cookie moka",9,[("cookie_un",1)],0.20),
]
print("\n"+"="*90); print("A LINHA CAFÉ E PADARIA — BASE PRONTA, LOUÇA DE SALÃO"); print("="*90)
print(f"  {'Item':<32}{'Venda':>8}{'Custo':>9}{'CMV':>7}{'Sobra':>9}{'Preço a 35%':>14}")
for n,p,c,cmv in sorted(ITENS,key=lambda x:-x[3]):
    alvo=f"→ {brl(round(c/.35))}" if cmv>.42 else ""
    print(f"  {n:<32}{brl(p):>8}{brl(c,2):>9}{pc(cmv,0):>7}{brl(p-c,2):>9}{alvo:>14}")
cafes=[i for i in ITENS if i[0] in ("Espresso","Cappuccino","Latte","Moka","Iced latte","Iced moka","Matcha latte","Chá da casa")]
comida=[i for i in ITENS if i not in cafes]
print(f"\n  Só bebida quente e gelada   CMV médio {pc(sum(c for _,_,c,_ in cafes)/sum(p for _,p,_,_ in cafes))}")
print(f"  Só comida                   CMV médio {pc(sum(c for _,_,c,_ in comida)/sum(p for _,p,_,_ in comida))}")
print(f"  Açaí self-service           CMV        26,2%")
print("\n  A massa terceirizada NÃO é o problema — ela custa R$ 2,10 num prato de R$ 16.")
print("  O que come a margem é o recheio caro: búfala a R$ 60/kg e presunto cru a R$ 90/kg")
print("  em porções de 40 a 60 g custam mais que a base inteira.")

# ── terceirizar contra padeiro, com o volume real ────────────────────────────
print("\n"+"="*90); print("TERCEIRIZAR CONTRA PADEIRO PRÓPRIO"); print("="*90)
VOL=[("Jan e fev",80,59),("Dezembro",60,31),("Mar e nov",35,61),("Abr a out",20,214)]
tot=sum(d*n for _,d,n in VOL)
for r,d,n in VOL: print(f"  {r:<14}{d:>4} itens/dia × {n:>3} dias = {d*n:>6,}".replace(",","."))
print(f"  {'ANO':<14}{'':>21}{tot:>6,}".replace(",","."))
DELTA=2.00
print(f"\n  Sobrepreço médio da base pronta            {brl(DELTA,2)} por item")
print(f"  Custo do sobrepreço no ano                 {brl(tot*DELTA)}")
print(f"  Custo de um padeiro CLT no ano             {brl(PADEIRO)}")
print(f"\n  Em insumo puro dá quase empate — {brl(tot*DELTA)} contra {brl(PADEIRO)}.")
print("  O que decide não é o insumo:")
print(f"    · {brl(CAPEX-12_000)} de forno, masseira e câmara que não cabem em 35 m²")
print("    · o padeiro é fixo o ano todo e a demanda vai de 80 itens/dia a 20")
print("    · fornada não vendida vira perda; base congelada não")
print("  Terceirizar está certo. Mas é empate no insumo, não folga — vale negociar o kg.")

print("\n"+"="*90); print("A MÁQUINA A R$ 160 — O QUE PERGUNTAR"); print("="*90)
print(f"  {'Café/kg':>10}{'Custo/xícara':>15}{'CMV do espresso':>18}{'8 kg/mês no ano':>19}")
for kg in (45,55,70,85):
    x=kg*0.018
    print(f"  {brl(kg):>10}{brl(x,2):>15}{pc(x/6,0):>18}{brl(kg*8*12):>19}")
print("\n  O aluguel a R$ 160 quase sempre vem com compra mínima de café atrelada —")
print("  é no preço do quilo que o fornecedor recupera a máquina.")
print("  Perguntar: volume mínimo/mês, preço do kg travado por quanto tempo,")
print("  manutenção e peça inclusas, prazo de contrato e multa por rescisão.")
print(f"  De R$ 55 para R$ 85 o kg são {brl(85*8*12-55*8*12)}/ano — vinte vezes o aluguel.")
