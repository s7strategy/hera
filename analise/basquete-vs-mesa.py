# -*- coding: utf-8 -*-
"""A máquina é do pai: capex zero, só frete.
Então a pergunta não é preço — é quanto custa o espaço que ela ocupa."""

FAT  = [170,130,55,25,16,15,17,15,17,24,45,110]   # R$ mil
MES  = "jan fev mar abr mai jun jul ago set out nov dez".split()
DIAS = [31,28,31,30,31,30,31,31,30,31,30,31]
TICKET   = 32
HORAS    = 13          # 7h às 20h no verão
ESTADIA  = 0.5         # hora sentado, média de uma açaiteria
SENTA    = 0.60        # fração que senta em vez de levar

# ── o que a máquina ocupa de verdade ──────────────────────────────────────────
MAQ_CHAO = 2.4 * 1.0           # o gabinete
MAQ_TIRO = 2.5 * 1.5           # a zona livre na frente, a bola sobe e volta
MAQ = MAQ_CHAO + MAQ_TIRO
MESA4 = 5.5                    # mesa de 4 com cadeiras e circulação

print("="*76)
print("O QUE ELA CUSTA EM CHÃO")
print("="*76)
print(f"gabinete            {MAQ_CHAO:>5.1f} m²")
print(f"zona de tiro        {MAQ_TIRO:>5.1f} m²   ← o que quase ninguém conta")
print(f"total               {MAQ:>5.1f} m²   =  {MAQ/MESA4:.1f} mesa de 4 lugares")

# ── a mesa perdida só custa dinheiro quando TODAS estão cheias ────────────────
print()
print("="*76)
print("MAS UMA MESA A MENOS SÓ CUSTA QUANDO O DECK ESTÁ LOTADO")
print("="*76)
for n_mesas in (6, 8, 10, 12):
    lug = n_mesas*4
    print(f"\n  Deck com {n_mesas} mesas ({lug} lugares) — perde 1, fica com {n_mesas-1}")
    print(f"  {'mês':6}{'cli/dia':>9}{'ocup. média':>13}{'ocup. no pico':>15}")
    for i,m in enumerate(MES):
        cli = FAT[i]*1000/TICKET/DIAS[i]
        # média do dia
        lugar_h_dia = cli*SENTA*ESTADIA
        ocup = lugar_h_dia/(lug*HORAS)
        # pico: 35% do movimento em 2 horas
        ocup_pico = (cli*.35*SENTA*ESTADIA)/(lug*2)
        if m in ("jan","fev","abr","jul","dez"):
            print(f"  {m:6}{cli:>9.0f}{ocup*100:>12.0f}%{ocup_pico*100:>14.0f}%")
    cli_jan = FAT[0]*1000/TICKET/DIAS[0]
    op = (cli_jan*.35*SENTA*ESTADIA)/(lug*2)
    veredito = "APERTA no pico" if op > .85 else ("fica justo" if op > .65 else "sobra mesa")
    print(f"  → em janeiro, no pico: {op*100:.0f}% dos lugares — {veredito}")

# ── o outro lado: ela trabalha justamente na hora do aperto ───────────────────
print()
print("="*76)
print("O QUE ELA DEVOLVE  ·  a fila é do balcão, não da mesa")
print("="*76)
cli_jan = FAT[0]*1000/TICKET/DIAS[0]
pico_dia = cli_jan*.35
print(f"Janeiro: {cli_jan:.0f} clientes/dia, {pico_dia:.0f} deles nas 2 h de pico.")
print()
print(f"{'desistência no pico':>22}{'perde/dia':>12}{'perde no verão':>17}{'se cair pela metade':>21}")
verao = sum(FAT[i]*1000/TICKET for i in (0,1,11))   # dez+jan+fev, clientes
for taxa in (.03,.05,.08,.12):
    dia = pico_dia*taxa*TICKET
    tot = verao*.35*taxa*TICKET
    print(f"{taxa*100:>20.0f}%{dia:>11.0f}{tot:>16,.0f}{tot/2:>20,.0f}".replace(",","."))
print("""
Quem desiste é quem olha a fila do caixa e vai embora — não quem não achou mesa.
É exatamente nesse minuto que 45 segundos de basquete seguram a pessoa.""")

# ── o segundo motivo, que é o de sempre no self-service ───────────────────────
print()
print("="*76)
print("E O QUE É PESO NA BALANÇA DEPOIS DE JOGAR")
print("="*76)
CLI_ANO = sum(FAT)*1000/TICKET
print(f"{CLI_ANO:,.0f} clientes/ano.".replace(",","."))
print(f"\n{'joga':>8}{'volta ao balcão':>18}{'a mais':>9}{'no ano':>13}")
for joga in (.08,.15,.25):
    for volta,mais in ((.30,6),):
        g = CLI_ANO*joga*volta*mais
        print(f"{joga*100:>7.0f}%{volta*100:>17.0f}%{'R$ '+str(mais):>9}{g:>13,.0f}".replace(",","."))
print("""
No self-service por peso isso é direto: quem joga, esquenta e volta a
colocar mais na tigela. Por isso a máquina fica LIVRE — cobrar R$ 3 de
ficha tira de alguém que ia gastar R$ 6 a mais no balcão.""")

print()
print("="*76)
print("O CUSTO QUE NÃO É DE CHÃO")
print("="*76)
print(f"""altura do gabinete    ~2,3 m
altura de uma mesa     ~0,8 m

Num deck de praia, o que se vende é a vista. Um armário preto de 2,3 m no
meio do deck corta o mar para metade das mesas — e isso não aparece em
nenhuma conta de m².

Por isso: canto ou fundo, nunca no meio, nunca entre as mesas e o mar.""")
