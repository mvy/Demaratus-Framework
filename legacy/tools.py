#!/usr/bin/python
# -*- coding: utf-8 -*-

""" Fonctions très utiles par Yves Stadler. Optimisations par Michaël Coquard.
    Remerciements spéciaux à D. Kratsch pour les cours d'algo pour le tri
    fusion :)."""

factCache = [1]

def fact(i) :
    """ Calcul de factorielle avec mise en cache des résultats. """
    n = len(factCache)
    if i >= n:
        while n <= i:
            factCache.append(factCache[n-1]*n)
            n += 1
    return factCache[i]

def unrank(x,l):
    """ Calcule la xième permutation de la liste l en tenant compte de l'ordre
        lexicographique des permutations. x == 0 correspond à la première
        permutations, c'est à dire la liste triée en ordre lexicographique.
        La liste l est supposée triée. """
    m = []
    n = len(l)
    f = fact(n)
    x = x % f
    while l:
        f /= n
        q,r = divmod(x,f)
        m.append(l.pop(q))
        n -= 1
        x = r
    return m
        
def rank(l):
    """ Fonction inverse de 'rank'. Cette fonction trouve à quelle indice
        se situe la permutation donnée en paramètre. L'ordre lexicographique des
        objets de la liste est utilisé pour retrouvé l'indice. """
    n = len(l)
    if n == 1 or n == 0:
        return 0 #une seule permutation possible !
    # REM : ici, on doit effectuer un tri sur la liste car on ne dispose pas des
    # indices absolus des éléments (on doit donc les comparer)
    # On peut peut être réduire le temps d'exécution qui est de O(n*n) en
    # utilisant un autre tri mais cela semble difficile (même avec un tri
    # récursif de type tri-fusion puisqu'il faut tenir compte du cout de
    # permutation pour calculer le rang)
    m = [l.pop()]
    r = 0
    n = 1
    # cout d'une permutation au départ
    cost = 1
    while l:
        e = l.pop()
        i = 0
        while (i < len(m)) and (m[i] < e):
            i += 1
            r += cost
        # élément en fin de liste
        if i == len(m):
            m.append(e)
        # insertion
        elif m[i] >= e:
            m.insert(i,e)
        n += 1
        cost *= n
    return r

def intToBinaryList(n,m):
    """ Converti un entier n en sa représentation binaire sous forme de liste.
        le bit de poids faible se trouve en fin de liste. m précise le nombre
        de bits qui doivent être récupérés du nombre n (en partant du bit de
        poids faible). """
    l = []
    mask = 1 << (m - 1)
    while mask:
        if n & mask:
            l.append(1)
        else:
            l.append(0)
        mask >>= 1
    return l



def XMLTagExtract(s):
    """ Parse une balise XML et retourne un triplet contenant dans l'ordre :
        - la liste des attributs de la balise sous forme de chaîne
        - la marque de début de balise (ex : '<html')
        - la marque de fin de balise.
        REM : on suppose que la balise est une balise xml valide. """
    SP = ['\n','\r','\t',' ']
    intag = False
    insep = False
    inval1 = False
    inval2 = False
    current = ""
    start = ""
    end = ""
    l = []
    for i in s:
        if inval1:
            current += i
            if i == "'":
                intag = False
                inval1 = False
                inval2 = False
                l.append(current)
                current = ""
        elif inval2:
            current += i
            if i == '"':
                intag = False
                inval1 = False
                inval2 = False
                l.append(current)
                current = ""
        elif intag:
            current += i
            if i == "'":
                inval1 = True
            if i == '"':
                inval2 = True
        elif insep:
            if not (i in SP):
                current += i
                intag = True
        elif i in SP:
            insep = True
            start = current
            current = ""
        else:
            current += i
    end = current
    return (l,start,end)

def intToHex(n,upper=False):
    """ Converti un entier sa représentation hexadécimale.
        le paramètre upper permet de spécifier si la représentation
        sera en majuscules (True) ou en minuscules (False) """
    if upper:
        num = "0123456789ABCDEF"
    else:
        num = "0123456789abcdef"
    result = ""
    while n != 0:
        result = num[n & 0xf] + result
        n >>= 4
    return result

if __name__=='__main__':
    print "Tools module by Yves Stadler and Michael Coquard"