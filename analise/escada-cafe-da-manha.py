# -*- coding: utf-8 -*-
"""Café da manhã do Airbnb: a escada de volume. O que cada degrau exige de
parceiros, de gente e de estrutura — e onde deixa de ser canal e vira negócio."""
def brl(v,c=0): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"

TICKET=90.50; SOBRA=42.37
PICO=60                    # 20/dez a 20/fev — os 60 dias que ele citou
OCUP=.92; ESTADIA=5        # janeiro
FERRUGEM=435               # anúncios listados na Praia da Ferrugem
GAROPABA=1_800             # estimativa do parque do município inteiro

def parceiros(pedidos_dia, conv, repete=.30):
    """Unidades parceiras necessárias para X pedidos/dia no pico."""
    ped_estadia=conv*(1+repete)
    return pedidos_dia/(OCUP/ESTADIA*ped_estadia)

print("="*94); print("QUANTOS PARCEIROS CADA VOLUME EXIGE, NO PICO DE JANEIRO"); print("="*94)
print(f"  {'Pedidos/dia':>12}"+"".join(f"{'conv '+pc(c):>16}" for c in (.15,.25,.40,.60)))
for pd in (10,30,60,100,200):
    linha=f"  {pd:>12}"
    for c in (.15,.25,.40,.60):
        u=parceiros(pd,c)
        onde="" if u<=FERRUGEM else "*"
        linha+=f"{f'{u:,.0f}'.replace(',','.')+onde:>16}"
    print(linha)
print(f"\n  * acima de {FERRUGEM} unidades a Ferrugem acabou — precisa Silveira, centro e Garopaba")
print(f"    inteira, um parque estimado em ~{GAROPABA:,} anúncios.".replace(",","."))
print("  conv = % das estadias que pedem ao menos uma vez; 30% dessas pedem uma segunda manhã.")

print("\n"+"="*94); print("A ESCADA — O QUE CADA DEGRAU EXIGE"); print("="*94)
DEGRAUS=[
 (10,"Canal","absorvido pela equipe","a loja, fora do pico","1 pessoa"),
 (30,"Canal","teto da loja atual","a loja, fora do pico","2 pessoas de manhã"),
 (60,"Operação","turno de manhã dedicado","área de montagem separada","3 a 4 pessoas"),
 (100,"Negócio","cozinha de apoio licenciada","endereço próprio com alvará","5 a 6 pessoas"),
 (200,"Negócio","cozinha central + frota","endereço próprio, 2 motos","9 a 12 pessoas"),
]
print(f"  {'/dia':>5}{'O que é':>11}{'Gargalo':>32}{'Onde monta':>30}{'Equipe':>20}")
for d,tipo,garg,onde,eq in DEGRAUS:
    print(f"  {d:>5}{tipo:>11}{garg:>32}{onde:>30}{eq:>20}")

print("\n"+"="*94); print(f"O DINHEIRO NOS {PICO} DIAS DE PICO"); print("="*94)
print(f"  {'/dia':>5}{'Caixas':>9}{'Faturamento':>14}{'Sobra bruta':>14}{'vs. a loja no ano':>20}")
LOJA_LUCRO=250_177
for d in (10,30,60,100,200):
    n=d*PICO
    print(f"  {d:>5}{n:>9,}{brl(n*TICKET):>14}{brl(n*SOBRA):>14}{n*SOBRA/LOJA_LUCRO:>19.1f}×".replace(",","."))
print(f"\n  A loja inteira dá {brl(LOJA_LUCRO)} de lucro no ano.")
print(f"  A 100/dia, os 60 dias de verão sozinhos passam disso.")

print("\n"+"="*94); print("O GARGALO REAL NÃO É VENDER — É ENTREGAR"); print("="*94)
print("  Montagem, caixa padronizada e pré-montada na véspera        90 s por caixa")
print("  Entrega de scooter, rota pré-ordenada, raio de 2 km         15 drops/hora")
print("  Janela de entrega                                           7h às 9h30\n")
print(f"  {'/dia':>5}{'Montagem':>18}{'Motos necessárias':>20}{'Pessoas de manhã':>19}")
for d in (10,30,60,100,200):
    horas_m=d*90/3600
    motos=max(1,-(-d//(15*2.5)))
    print(f"  {d:>5}{f'{horas_m:.1f} h na véspera':>18}{motos:>20}{max(1,-(-d//25))+motos:>19}")
print("\n  A 200/dia são 5 horas de montagem na véspera e 6 motos em duas horas e meia.")
print("  Em janeiro essa gente concorre com as 5 pessoas que o balcão já precisa.")

print("\n"+"="*94); print("O TETO DA FERRUGEM SOZINHA"); print("="*94)
def por_dia(u,conv,repete=.30): return u*OCUP/ESTADIA*conv*(1+repete)
print(f"  {'Conversão':<12}{'Ferrugem inteira (435)':>26}{'Garopaba inteira (1.800)':>28}")
for c in (.15,.25,.40,.60):
    print(f"  {pc(c):<12}{por_dia(FERRUGEM,c):>21.0f}/dia{por_dia(GAROPABA,c):>23.0f}/dia")
print("\n  Assinando TODOS os 435 anúncios da Ferrugem, na conversão do plano, dá 16 caixas/dia.")
print("  É esse o teto do bairro. Para passar dele há dois caminhos, e eles se somam:")
print("    · subir a conversão — a Ferrugem a 40% já dá 42/dia")
print("    · sair da Ferrugem — Silveira, centro e Garopaba multiplicam o parque por 4")

print("\n"+"="*94); print("POR QUE 40% DE CONVERSÃO É DEFENSÁVEL"); print("="*94)
print("  A oferta não é 'café da manhã'. É a PRIMEIRA MANHÃ da estadia.")
print("  A família chega sexta à noite, geladeira vazia, mercado a 10 minutos e lotado em janeiro.")
print("  Vender a manhã da chegada é uma dor universal e datada — não depende de gosto.")
print("  Uma estadia tem 1 manhã de chegada e 4 manhãs comuns. A de chegada converte muito mais.")
print(f"\n  {'Cenário':<44}{'Pedidos/dia no pico':>22}")
for rot,u,c in [("Ferrugem, metade assinada, conversão do plano",218,.15),
                ("Ferrugem inteira, conversão do plano",435,.15),
                ("Ferrugem inteira, manhã da chegada a 40%",435,.40),
                ("Ferrugem + Silveira + centro (900), a 40%",900,.40),
                ("Garopaba inteira (1.800), a 40%",1800,.40),
                ("Garopaba inteira, a 60%",1800,.60)]:
    print(f"  {rot:<44}{por_dia(u,c):>17.0f}/dia")

print("\n"+"="*94); print("A RESPOSTA"); print("="*94)
print("  100 a 200 por dia em 60 dias não é fantasia — é o cenário 'Garopaba inteira a 40 a 60%'.")
print("  Mas não é o primeiro verão, por quatro motivos que se somam:")
print("    1. exige ~93% do parque do município assinado, não da Ferrugem")
print("    2. exige cozinha de apoio licenciada — 100 caixas não cabem nos 35 m²")
print("    3. exige 3 motos e 7 pessoas na manhã, sem tirar ninguém do balcão")
print("    4. exige conversão medida, e ninguém tem esse número ainda")
print("\n  Plano de dois tempos:")
print(f"    Verão 1 — Ferrugem, meta de 200 parceiros e {por_dia(200,.15):.0f} a {por_dia(200,.40):.0f} caixas/dia.")
print("             O objetivo do ano 1 não é faturar, é MEDIR a conversão real.")
print(f"    Verão 2 — com o número na mão, Garopaba inteira e cozinha de apoio.")
print(f"             A {por_dia(1800,.40):.0f} caixas/dia os 60 dias de pico fazem {brl(por_dia(1800,.40)*60*SOBRA)} de sobra.")
print(f"             Mais que o dobro do lucro anual da loja inteira.")
