# -*- coding: utf-8 -*-
"""Café da manhã do Airbnb: a escada de volume. O que cada degrau exige de
parceiros, de gente e de estrutura — e onde deixa de ser canal e vira negócio."""
def brl(v,c=0): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"

TICKET=90.50; SOBRA=42.37
PICO=60                    # 20/dez a 20/fev — os 60 dias que ele citou
OCUP=.92; ESTADIA=5        # janeiro
# ── o tamanho do parque é a premissa que mais pesa, e ainda não está medida ──
# 435 era o número de anúncios COM ESTACIONAMENTO num agregador — contador de
# filtro, não total. Busca própria do dono na Ferrugem devolveu ~1.600.
FERRUGEM_MIN=435           # piso: contagem filtrada de um agregador
FERRUGEM=1_600             # busca do dono na Praia da Ferrugem
GAROPABA=4_000             # município inteiro, escalado na mesma proporção

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
print(f"\n  * acima de {FERRUGEM:,} unidades a Ferrugem acabou — precisa Silveira, centro e Garopaba".replace(",","."))
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
print(f"  {'Conversão':<12}{'Se forem 435':>18}{'Se forem 1.600':>18}{'Garopaba (4.000)':>20}")
for c in (.15,.25,.40,.60):
    print(f"  {pc(c):<12}{por_dia(FERRUGEM_MIN,c):>13.0f}/dia{por_dia(FERRUGEM,c):>13.0f}/dia{por_dia(GAROPABA,c):>15.0f}/dia")
print("\n  A diferença entre 435 e 1.600 é a diferença entre um canal e um negócio.")
print("  Nenhum dos dois números está medido — o de 435 veio de um filtro de agregador")
print("  ('com estacionamento'), o de 1.600 de uma busca no Airbnb, que varre um raio")
print("  maior que o bairro. O número real precisa vir de uma fonte que conte de verdade.")

print("\n"+"="*94); print("POR QUE 40% DE CONVERSÃO É DEFENSÁVEL"); print("="*94)
print("  A oferta não é 'café da manhã'. É a PRIMEIRA MANHÃ da estadia.")
print("  A família chega sexta à noite, geladeira vazia, mercado a 10 minutos e lotado em janeiro.")
print("  Vender a manhã da chegada é uma dor universal e datada — não depende de gosto.")
print("  Uma estadia tem 1 manhã de chegada e 4 manhãs comuns. A de chegada converte muito mais.")
print(f"\n  {'Cenário':<44}{'Pedidos/dia no pico':>22}")
for rot,u,c in [("Ferrugem, 400 assinados, conversão do plano",400,.15),
                ("Ferrugem, 400 assinados, manhã da chegada a 40%",400,.40),
                ("Ferrugem, 800 assinados (50%), a 40%",800,.40),
                ("Ferrugem, 1.000 assinados (63%), a 40%",1000,.40),
                ("Ferrugem inteira (1.600), a 40%",1600,.40),
                ("Ferrugem inteira, a 60%",1600,.60)]:
    print(f"  {rot:<44}{por_dia(u,c):>17.0f}/dia")

print("\n"+"="*94); print("A RESPOSTA, COM O PARQUE DE 1.600"); print("="*94)
print(f"  {'Meta':>9}{'Parceiros a 25%':>18}{'a 40%':>12}{'a 60%':>12}{'% da Ferrugem a 40%':>22}")
for pd in (30,60,100,200):
    u25,u40,u60=parceiros(pd,.25),parceiros(pd,.40),parceiros(pd,.60)
    print(f"  {pd:>6}/dia{u25:>18,.0f}{u40:>12,.0f}{u60:>12,.0f}{u40/FERRUGEM*100:>21.0f}%".replace(",","."))
print("\n  100/dia deixa de exigir o município inteiro: pede ~65% da Ferrugem a 40% de conversão,")
print("  ou ~44% dela a 60%. Isso é meta de temporada, não de década.")
print("  200/dia pede a Ferrugem quase inteira a 60%, ou esticar para Silveira e centro.")

print("\n"+"="*94); print("MAS O NÚMERO PRECISA SER MEDIDO ANTES DE VIRAR PLANO"); print("="*94)
print("  Nenhuma das duas contagens serve para decidir investimento:")
print("    · 435 era filtro de agregador, não total")
print("    · a busca do Airbnb varre um raio maior que o bairro e conta anúncio, não imóvel")
print("      (o mesmo imóvel aparece em Airbnb, Booking e imobiliária)")
print("\n  Quatro fontes que dão número de verdade, em ordem de esforço:")
print("    1. As gestoras. Três conversas: quantas unidades cada uma administra e quanto")
print("       estimam do total. Já estão no plano de qualquer forma — é pergunta de graça.")
print("    2. A prefeitura de Garopaba. Cadastro de locação por temporada, se existir,")
print("       ou o número de alvarás e a base de IPTU não residencial da orla.")
print("    3. AirDNA ou Mashvisor. Dão contagem de anúncios ativos e ocupação real do")
print("       mercado. Custa, mas resolve a premissa mais cara do plano.")
print("    4. Contagem manual no mapa do Airbnb com o zoom travado só na Ferrugem,")
print("       em janeiro e em junho, para separar anúncio ativo de anúncio dormindo.")
print("\n  Enquanto o número não vier, o plano roda com 400 parceiros como meta do verão 1.")
print(f"  A 40% de conversão isso já dá {por_dia(400,.40):.0f} caixas/dia — {por_dia(400,.40)*60*SOBRA:,.0f} de sobra nos 60 dias.".replace(",","."))
