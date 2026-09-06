# -*- coding: utf-8 -*-
"""A caixa moka de café da manhã, 2 pessoas. Conteúdo fechado com o dono,
mais o que faltava. Preço de atacado em volume."""
def brl(v,c=2): return ("R$ %s"%f"{v:,.{c}f}").replace(",","·").replace(".",",").replace("·",".")
def pc(v,c=0): return f"{v*100:.{c}f}%"

# (bloco, item, quantidade, custo, nota)
CAIXA=[
 ("PÃO","2 fatias de pão de fermentação longa","120 g",1.92,"R$ 16/kg no atacado, negociado"),
 ("PÃO","2 mini croissants","2 un",4.00,""),
 ("PROTEÍNA","2 ovos cozidos, com casca","2 un",1.80,"⚠ cozido. Mexido ou frito chega borrachudo"),
 ("PROTEÍNA","Queijo colonial","60 g",2.16,"R$ 36/kg atacado SC"),
 ("PROTEÍNA","Peito de peru","60 g",1.92,""),
 ("POTINHOS","Geleia em mini-pote de hotel","25 g",1.20,"comprado pronto — envasar exige área licenciada"),
 ("POTINHOS","Manteiga em tablete","2×10 g",0.92,"⚠ passada no pão encharca em 2h"),
 ("POTINHOS","Pesto, envasado na loja","30 g",2.05,"R$ 1,80 de pesto + R$ 0,25 de pote"),
 ("FRUTA","Meio avocado, com casca e caroço","150 g",2.70,"⚠ cortado oxida. Inteiro o hóspede abre"),
 ("FRUTA","Fruta da estação","200 g",1.00,"banana, mamão ou melão"),
 ("DOCE","2 mini cookies","2 un",2.40,"escolher: cookie OU bolo, não os dois"),
 ("BEBIDA","Café da casa em garrafa térmica","500 ml",1.80,"36 g de grão"),
 ("+ MOKA","Iogurte natural com mel","100 g",1.80,"é o que fecha o café da manhã da Califórnia"),
 ("+ MOKA","Granola da casa","30 g",0.60,"já está no balcão do açaí"),
 ("+ MOKA","Sal e pimenta em sachê","2+2",0.10,"para o ovo e o avocado. Ninguém põe e faz diferença"),
 ("+ MOKA","Cartão com o nome do hóspede","1",0.20,"é o que vira foto no Instagram"),
]
EMB=[
 ("Caixa kraft + adesivo da marca","1",1.50),
 ("2 marmitinhas com tampa","2",0.70),
 ("Garrafa térmica em comodato","1",0.48,),
 ("Papel manteiga, guardanapo, talheres","—",0.55),
 ("Sacola kraft","1",0.45),
]

print("="*92); print("A CAIXA MOKA · CAFÉ DA MANHÃ PARA 2"); print("="*92)
bloco=None; ins=0
for b,d,q,c,n in CAIXA:
    if b!=bloco: print(f"\n  {b}"); bloco=b
    print(f"    {d:<42}{q:>9}{brl(c):>10}   {n}")
    ins+=c
print(f"\n  {'':<44}{'INSUMO':>9}{brl(ins):>10}")

print(f"\n  EMBALAGEM")
emb=0
for d,q,c in EMB:
    print(f"    {d:<42}{q:>9}{brl(c):>10}")
    emb+=c
print(f"  {'':<44}{'EMBALAGEM':>9}{brl(emb):>10}")

CUSTO=(ins+emb)*1.03
print(f"\n  {'':<44}{'CUSTO':>9}{brl(CUSTO):>10}   com 3% de quebra")
print(f"  {'':<44}{'':>9}{'':>10}   copo descartável: R$ 0,00 — a térmica volta")

print("\n"+"="*92); print("O PREÇO QUE ISSO PEDE"); print("="*92)
ENT=2.50; COM=.15
print(f"  {'Preço':>8}{'CMV':>8}{'Entrega':>10}{'Comissão':>11}{'Sobra':>11}{'Margem':>9}{'vs tigela de açaí':>20}")
for p in (89,99,109,119):
    s=p-CUSTO-ENT-p*COM
    print(f"  {brl(p,0):>8}{pc(CUSTO/p):>8}{brl(ENT):>10}{brl(p*COM):>11}{brl(s):>11}{pc(s/p):>9}{s/22.95:>17.1f}×")
print(f"\n  A R$ 99 a caixa sobra {brl(99-CUSTO-ENT-99*COM)} — mais que o dobro de uma tigela de açaí,")
print(f"  às 8h da manhã, com o balcão parado.")

print("\n"+"="*92); print("AS CINCO PEGADINHAS TÉCNICAS"); print("="*92)
print("""  1. MANTEIGA PASSADA NO PÃO
     Em 2 horas a manteiga encharca o miolo do pão de fermentação natural e ele
     murcha. E pão com manteiga passada vira alimento manipulado pronto para
     consumo — outra classificação sanitária e outro prazo.
     → Tablete ao lado, ou um terceiro potinho. O pão chega inteiro e a conta
       é a mesma. Se quiser mesmo passada, tem que ser na hora da entrega.

  2. AVOCADO CORTADO OXIDA
     Fica marrom em 1 a 2 horas mesmo com limão. Chega feio na foto.
     → Meio avocado com casca e caroço. O hóspede abre. Zero oxidação, mais
       bonito, e é o mesmo custo.

  3. O OVO TEM QUE SER COZIDO
     Mexido ou frito chega borrachudo e frio. Cozido com casca é clássico de
     café da manhã europeu e viaja perfeito.
     → Mas precisa ir refrigerado até a entrega. Em janeiro, a 30 °C, a caixa
       montada às 5h e entregue às 8h fica 3 horas fora da geladeira. Monta
       refrigerado e fecha na hora de sair.

  4. CROISSANT + PÃO + COOKIE + BOLO É CARBOIDRATO DEMAIS
     Você mesmo desconfiou. São quatro farináceos numa caixa para duas pessoas.
     → Ficaram cookie e croissant, saiu o bolo. Se quiser o bolo, tira o cookie.

  5. ENVASAR POTINHO EXIGE ÁREA LICENCIADA
     Geleia envasada por vocês é manipulação. Comprada em mini-pote de hotel,
     não é — e ainda sai mais barata (R$ 1,20 os 25 g contra R$ 1,93 envasando 60 g).
     → Geleia comprada pronta. Pesto e manteiga envasados na cozinha da loja,
       que é licenciada. Nunca em casa.""")

print("\n"+"="*92); print("SOBRE OS POTINHOS"); print("="*92)
print("""  Pote PP 30-60 ml com tampa de rosca, atacado 1.000+     R$ 0,18 a 0,35
  Pote de alumínio com tampa de papel, tipo hotel          R$ 0,25
  Pote de vidro 40 ml, mais bonito e mais caro             R$ 1,20 a 2,00
  Geleia já em mini-pote de marca (Queensberry, Dallas)    R$ 1,20 a 1,80

  Para pesto e manteiga: PP de 30 ml, R$ 0,25. Envasado na loja.
  Para geleia: comprar pronta. Marca boa agrega valor e evita a manipulação.""")

print("\n"+"="*92); print("CORTAR O INDIVIDUAL FOI DECISÃO CERTA"); print("="*92)
print(f"""  Um kit solo de R$ 45 usa a MESMA caixa, a MESMA entrega e paga a MESMA
  comissão de 15% de um kit de R$ 99. A entrega e a embalagem são custo fixo
  por pedido, não por pessoa.

  Solo a R$ 45     custo ~R$ 20   entrega R$ 2,50   comissão R$ 6,75   sobra R$ 15,75
  Casal a R$ 99    custo {brl(CUSTO)}   entrega R$ 2,50   comissão R$ 14,85  sobra {brl(99-CUSTO-2.50-14.85)}

  A mesma moto, o mesmo minuto de montagem, três vezes menos sobra.
  Duas faixas — casal e família — é o desenho certo.""")
