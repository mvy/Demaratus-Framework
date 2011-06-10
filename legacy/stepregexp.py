#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Step By Step Regular expressions module by Michaël Coquard

Ce module permet de compiler des expressions régulières utilisables pour
reconnaitre des chaînes partielles (caractère par caractère)

Les caractères à tester doivent être donnés en ASCII
(un caractère = un octet). Ceci est aussi valable pour les expressions
régulières elle-mêmes.

Les opérateurs reconnus se limitent pour l'instant aux opérateurs suivants :
    
()      qui permet de grouper des expressions
|       pour réaliser un 'ou' entre deux expressions
.       pour signifier n'importe quel caractère
+       l'expression qui précède devra être présente et pourra être répétée
        plusieurs fois
*       l'expression qui précède pourra ou non être présente et répétée
        plusieurs fois
?       l'expression qui précède pourra être présente ou non
[ ]     signifie un caractère parmis ceux entre crochets
[^ ]    signifie un caractère non présent dans ceux données entre crochets
[A-Z]   Il est possible de spécifier des intervalles de caractères (ordre ASCII)
\\      permet d'échapper un caractère spécial (il faut doubler l'antislash car
        il est déjà considéré comme caractère spécial dans une chaîne pour
        python)
        EX: \\* permet de reconnaître le caractère '*'

Un grand merci à Mr Cansell pour son cours sur la théorie des langages qui m'a
bien servie ici :)

L'algorithme d'auto-déterminisation de l'automate s'inspire du code donné par
Russ Cox dans son article 'Regular Expression Matching Can Be Simple And Fast'.
Ceci permet une exécution très rapide (beaucoup plus que le module de python
non-déterministe).
"""

__all__ = ["Pattern","compile","RegexpException"]

# Les automates à état finis sont stockés sous forme de graphe avec des
# listes de pointeurs
#
# Ils sont représentés par un classe représentant un état de l'automate.
# Il existe deux classes, l'une pour la représentation des automates
# non-déterministes et l'autre pour la représentation des automates
# déterministes, respectivement 'NDState' et 'DState'. Les états contiennent
# des pointeurs vers les états suivants de l'automate.
#
# Un automate correspond simplement à un pointeur sur un état : son état
# initial.
#
# Un token représente une lettre de l'alphabet à reconnaître. Chaque transition
# se fait sur un token particulier. Les tokens sont codés par des entiers.
# Comme il existe des tokens particuliers, on doit découper ces entiers en
# champs de bits :
# - les 8 bits de poid faible sont réservés au codage de l'octet/caractère
#   qui doit être reconnu (masque 0x000000FF)
# - le bit 9 est réservé pour signaler une transition valable pour tout
#   caractère (masque 0x00000100)
# - le bit 10 indique que l'état est final (masque 0x00000200)
# - le bit 11 est réservé pour signaler une transition Epsilon dans les
#   automates non-déterministes (masque 0x00000400)
#

# Flags utilisés pour décoder un token

BYTE_MASK = 0x000000FF # 255
FLAG_ANY = 0x00000100 # 256
FLAG_FINAL = 0x00000200 # 512
FLAG_EPSILON = 0x00000400 # 1024

# Classes pour la représentation des automates non-déterministes

class NDState:
    """ Représente un état d'un automate à états finis non déterministe. """
    def __init__(self,next1,next2,t):
        self.next1 = next1
        self.next2 = next2
        self.t = t
        # marque qui sera utilisée pour déterminiser l'automate
        self.markid = id(None)

# Classes pour la représentation des automates déterministes

class DState:
    """ Représente un état d'un automate à états finis déterministe. """
    def __init__(self,ndstates,final=False):
        self.trans = [None]*256
        self.final = final
        # états de l'automate non déterministe associé
        self.ndstates = ndstates
        # pointeurs gauche et droit pour classer ces états dans un arbre
        # ceci sera utilisé dans la déterminisation de l'automate
        self.g = None
        self.d = None

PASS = 0
FAIL = 1
ACCEPT = 2

def eclosure(ndstates):
    """ Epsilon-closure d'un ensemble d'états.
        Cette fonction renvoie un couple (l,b) où l est
        l'epsilon-closure de la liste d'états states et b indique si cet
        ensemble possède au moins un état final (True) ou si il n'y a
        aucun état final (False). """
    # liste des états de la closure
    l = ndstates
    b = False
    for s in ndstates:
        # si l'état courant est final, on indique que toute la closure sera
        # équivalente à un état final
        if s.t & FLAG_FINAL:
            b = True
        # sinon on visite les "fils" de l'état courant (si celui-ci est un état
        # epsilon)
        elif s.t & FLAG_EPSILON:
            # pour chaque fils, on regarde s'il est marqué. La marque est un
            # pointeur sur la liste des états de l'epsilon-closure. Ceci permet
            # de savoir si l'état se trouve déjà dans la liste !
            if (s.next1.markid != id(l)):
                s.next1.markid = id(l)
                l.append(s.next1)
            if (s.next2 != None) and (s.next2.markid != id(l)):
                s.next2.markid = id(l)
                l.append(s.next2)
    return (l,b)

class Pattern:
    """ Représente une expression régulière compilée """
    def __init__(self,beginState):
        """ Constructeur privé ! beginState correspond à l'état initial de
            l'automate non-déterministe associé. """
        self.ndstates = beginState
        # initialisation du premier état déterministe
        initialClosure,final = eclosure([beginState])
        initialClosure.sort()
        self.beginState = DState(initialClosure,final)
        self.currentState = self.beginState
        # sommet de l'arbre binaire pour classer les états déterministes
        self.allDStates = self.beginState
        self.loose = False
    def reset(self):
        """ Remet l'expression régulière dans son été initial. """
        self.currentState = self.beginState
        self.loose = False
    def next(self,c):
        """ Injecte un caractère dans l'expression régulière compilée.
            Si l'expression reconnait le caractère, celle-ci retourne le code
            PASS, si l'expression a reconnu toute une chaîne le code ACCEPT sera
            retourné. Si le caractère ne correspond pas le code FAIL sera
            retourné. Si caractère n'est pas reconnu, tous les appels suivants
            à cette méthode retourneront FAIL, il faudra réinitialiser
            l'expression compilée à l'aide de la méthode reset(). """
        if self.loose:
            return FAIL
        c = ord(c)
        # si un état déterministe existe pour le token, il suffit de le prendre
        if self.currentState.trans[c] != None:
            self.currentState = self.currentState.trans[c]
            if self.currentState.final:
                return ACCEPT
            return PASS
        # sinon, nous devons calculer l'état suivant en utilisant l'automate
        # non-déterministe associé
        # on utilise l'epsilon closure de l'état déterministe courant pour
        # calculer un nouvel ensemble d'états
        l = []
        for s in self.currentState.ndstates:
            # si la transition est bonne
            if (s.t & ~FLAG_EPSILON) and ((s.t & FLAG_ANY) or (s.t & BYTE_MASK) == c):
                l.append(s.next1)
        # si la liste est vide, aucune transition n'a pu être trouvée le
        # caractère n'est donc pas reconnu
        if not l:
            self.loose = True
            return FAIL
        # on étend cet ensemble à son epsilon closure
        l,b = eclosure(l)
        # l'ensemble doit être ordonné pour pouvoir être comparé
        l.sort()
        # on recherche l'existance de cet ensemble et de son état déterministe
        # correspondant dans l'arbre
        node = self.allDStates
        # on doit récupérer le dernier noeud visité car on n'a pas de pointeur
        # de pointeur en python...
        lastnode = None
        while node != None:
            lastnode = node
            comp = cmp(l,node.ndstates)
            if comp < 0:
                node = node.g
            elif comp > 0:
                node = node.d
            else:
                next = node
                # très important, il faut remplacer l'ancienne liste par la
                # nouvelle même si elles sont identiques. Ceci permet de
                # conserver la dernière adresse mémoire et donc l'identifiant
                # utilisé pour calculer l'epsilon-closure !!!
                node.ndstates = l
                break
        else:
            # si on n'a pas trouvé l'état, on en crée un nouvel
            # on l'ajoute dans l'arbre binaire
            node = DState(l,b)
            if comp < 0:
                lastnode.g = node
            else:
                lastnode.d = node
        # on chaîne l'état trouvé ou crée avec l'état déterministe courant
        self.currentState.trans[c] = node
        self.currentState = node
        if node.final:
            return ACCEPT
        return PASS
    def isAccepted(self):
        """ Retourne True si l'état courant est un état final, False sinon. """
        return self.currentState.final and not self.loose

class RegexpException(Exception):
    """ Exceptions pour les expressions régulières."""
    def __init__(self,s):
        Exception.__init__(self,s)
        
    
SPECIAL_CHARS = ['(',')','|','+','*','?','[',']','^']


# Grammaire des expressions régulières :
# E -> <token> F | <dot> | (E)
# F -> EF | E<or>EF | FE? | E*F | E+F | <epsilon>


class Tokenizer:
    """ Permet d'extraire un à un les tokens (caractères significatifs).
        d'une chaîne de type expressions régulière. Un token représente tout
        caractère différent de '\' ou deux caractères dont le premier est '\'.
        Ceci permet de gérer l'échappement des caractères propres aux
        expressions régulières. """
    def __init__(self,s):
        self.s = s
        self.i = 0
        self.l = len(s)
    def get(self):
        """ Retourne le token courant ou None si on se trouve en fin de chaîne.
            """
        if self.i == self.l:
            return None
        if self.s[self.i] == "\\":
            if self.i >= self.l - 1:
                raise RegexpException("'\\' cannot be placed at the end of the string")
            else:
                return self.s[self.i:self.i+2]
        return self.s[self.i]
    def next(self):
        """ Retourne le token courant puis avance d'une position dans la chaîne.
            """
        if self.i == self.l:
            current = None
        elif self.s[self.i] == "\\":
            if self.i >= self.l - 1:
                raise RegexpException("'\\' cannot be placed at the end of the string")
            else:
                current = self.s[self.i:self.i+2]
                self.i += 2
        else:
            current = self.s[self.i]
            self.i += 1
        return current


def compile(s):
    """ Compile une expression régulière donnée sous forme de chaîne. """
    t = Tokenizer(s)
    # Et une grammaire LL1 calculée à la main ! une !
    def E1():
        if t.get()=='[' or t.get()=='(' or t.get()=='.' or not (t.get() in SPECIAL_CHARS) and (t.get() != None):
            expr1 = T1()
            expr2 = E2()
            if expr2 == None:
                return expr1
            return Or(expr1,expr2)
        else:
            if t.get() != None:
                raise RegexpException("Syntax error near '"+str(t.get())+"'")
            else:
                raise RegexpException("Syntax error")
    def E2():
        if t.get()=='|':
            t.next()
            expr1 = T1()
            expr2 = E2()
            if expr2 == None:
                return expr1
            return Or(expr1,expr2)
    def T1():
        if t.get()=='[' or t.get()=='(' or t.get()=='.' or not (t.get() in SPECIAL_CHARS) and (t.get() != None):
            expr1 = F1()
            expr2 = T2()
            if expr2 == None:
                return expr1
            return And(expr1,expr2)
        else:
            if t.get() != None:
                raise RegexpException("Syntax error near '"+str(t.get())+"'")
            else:
                raise RegexpException("Syntax error")
    def T2():
        if t.get()=='[' or t.get()=='(' or t.get()=='.' or not (t.get() in SPECIAL_CHARS) and (t.get() != None):
            expr1 = F1()
            expr2 = T2()
            if expr2 == None:
                return expr1
            return And(expr1,expr2)
    def F1():
        if t.get()=='(':
            t.next()
            expr1 = E1()
            if t.get()==')':
                t.next()
                expr2 = F2(expr1)
                if expr2 != None:
                    return expr2
                return expr1
            else:
                raise RegexpException("Syntax error : ')' missing")
        elif t.get()=='.':
            expr1 = TokenAny()
            t.next()
            expr2 = F2(expr1)
            if expr2 == None:
                return expr1
            return expr2
        elif not (t.get() in SPECIAL_CHARS) and (t.get() != None):
            #traitement du '\'
            c = t.get()
            if c[0] == '\\':
                expr1 = Token(c[1])
            else:
                expr1 = Token(c)
            t.next()
            expr2 = F2(expr1)
            if expr2 == None:
                return expr1
            return expr2
        elif t.get()=='[':
            t.next()
            expr1 = G1()
            if t.get() == ']':
                t.next()
                expr2 = F2(expr1)
                if expr2 != None:
                    return expr2
                return expr1
            else:
                raise RegexpException("Syntax error : ']' missing")
        else:
            if t.get() != None:
                raise RegexpException("Syntax error near '"+str(t.get())+"'")
            else:
                raise RegexpException("Syntax error")
    def F2(expr):
        if t.get()=='?':
            t.next()
            expr2 = F2(expr)
            if expr2 != None:
                return Option(expr2)
            else:
                return Option(expr)
        elif t.get()=='*':
            t.next()
            expr2 = F2(expr)
            if expr2 != None:
                return Repete(expr2)
            else:
                return Repete(expr)
        elif t.get()=='+':
            t.next()
            expr2 = F2(expr)
            if expr2 != None:
                return RepeteOnce(expr2)
            else:
                return RepeteOnce(expr)
    def G1():
        if t.get()=='^':
            t.next()
            if (t.get() != None):
                c = t.get()
                if c[0] == '\\':
                    c = c[1]
                t.next()
                return TokenGroup(G2(c,True),True)
        elif (t.get() != None):
            c = t.get()
            if c[0] == '\\':
                c = c[1]
            t.next()
            return TokenGroup(G2(c,False),False)
        else:
            if t.get() != None:
                raise RegexpException("Syntax error near '"+str(t.get())+"'")
            else:
                raise RegexpException("Syntax error")
            
    def G2(pred,negate):
        if t.get() == '-':
            t.next()
            if t.get() != ']' and (t.get() != None):
                c = t.get()
                if c[0] == '\\':
                    c = c[1]
                t.next()
                # on regarde si les caractères sont dans l'intervalle
                if pred > c:
                    raise RegexpException("Bad characters interval. ")
                l = [chr(i) for i in range(ord(pred),ord(c)+1)]
                if t.get() != ']' and (t.get() != None):
                    c = t.get()
                    if c[0] == '\\':
                        c = c[1]
                    t.next()
                    l += G2(c,negate)
            elif t.get() == ']':
                #cas où le groupe se termine par un '-'
                l = ['-']
            return l
        elif t.get() != ']' and (t.get() != None):
            c = t.get()
            l = [pred]
            if c[0] == '\\':
                c = c[1]
            t.next()
            l += G2(c,negate)
            return l
        else:
            return [pred]
            
    #ouf c'est terminé :)
    expr = E1()
    if t.get() != None:
        raise RegexpException("Syntax error near '"+str(t.get())+"'")
    return Pattern(expr.compile()[0])

# Classes pour construire l'arbre syntaxique des expressions régulières

class Regexp:
    def compile(self,e):
        """ Méthode abstraite. Pour chaque expression régulière, cette méthode
            crée un automate non-déterministe et retourne un couple (init,final)
            correpondant à un pointeur vers l'état initial et à un pointeur
            vers l'état final de l'automate crée. """
        pass

# *
class Repete(Regexp):
    def __init__(self,e):
        self.e = e
    def compile(self):
        init1,final1 = self.e.compile()
        final = NDState(None,None,FLAG_FINAL)
        init = NDState(init1,final,FLAG_EPSILON)
        final1.t = FLAG_EPSILON
        final1.next1 = final
        final1.next2 = init1
        return (init,final)
    def __str__(self):
        return self.e.__str__()+"*"
# +
class RepeteOnce(Regexp):
    def __init__(self,e):
        self.e = e
    def compile(self):
        init1,final1 = self.e.compile()
        final = NDState(None,None,FLAG_FINAL)
        final1.t = FLAG_EPSILON
        final1.next1 = init1
        final1.next2 = final
        return (init1,final)
    def __str__(self):
        return self.e.__str__()+"+"

# |
class Or(Regexp):
    def __init__(self,e1,e2):
        self.e1 = e1
        self.e2 = e2
    def compile(self):
        init1,final1 = self.e1.compile()
        init2,final2 = self.e2.compile()
        init = NDState(init1,init2,FLAG_EPSILON)
        final1.t = FLAG_EPSILON
        final1.next1 = final2
        return (init,final2)
    def __str__(self):
        return "("+self.e1.__str__()+"|"+self.e2.__str__()+")"

# (concaténation)
class And(Regexp):
    def __init__(self,e1,e2):
        self.e1 = e1
        self.e2 = e2
    def compile(self):
        init1,final1 = self.e1.compile()
        init2,final2 = self.e2.compile()
        final1.t = init2.t
        final1.next1 = init2.next1
        final1.next2 = init2.next2
        # l'état init2 pourrait être détruit
        return (init1,final2)
    def __str__(self):
        return self.e1.__str__()+self.e2.__str__()

# ?
class Option(Regexp):
    def __init__(self,e):
        self.e = e
    def compile(self):
        init1,final1 = self.e.compile()
        init = NDState(init1,final1,FLAG_EPSILON)
        return (init,final1)
    def __str__(self):
        return self.e.__str__()+"?"

# caractère ASCII simple
class Token(Regexp):
    def __init__(self,c):
        self.token = ord(c)
    def compile(self):
        final = NDState(None,None,FLAG_FINAL)
        return (NDState(final,None,self.token),final)
    def __str__(self):
        return chr(self.token)
# .
class TokenAny(Regexp):
    def compile(self):
        f = NDState(None,None,FLAG_FINAL)
        return (NDState(f,None,FLAG_ANY),f)
    def __str__(self):
        return "."

# groupe de caractères ASCII [ ] et sa négation [^ ]
class TokenGroup(Regexp):
    def __init__(self,list,negate=False):
        self.list = list
        self.negate = negate
    def compile(self):
        if self.negate:
            l = [chr(i) for i in range(256) if not (chr(i) in self.list)]
        else:
            l = self.list
        # création des états
        final = NDState(None,None,FLAG_FINAL)
        init = NDState(final,None,ord(l[0]))
        for i in l[1:]:
            final.t = FLAG_EPSILON
            final2 = NDState(None,None,FLAG_FINAL)
            state = NDState(final2,None,ord(i))
            init = NDState(state,init,FLAG_EPSILON)
            final.next1 = final2
            final = final2
        return(init,final)
    def __str__(self):
        result = "["
        if self.negate:
            result += "^"
        for i in self.list:
            result += i
        return result + "]"

# Fonctions de débug

def printFSAND(a):
    """ Affiche la représentation mémoire d'un automate à état finis
        non-déterministe. """
    result = ""
    l = [a]
    i = 0
    while i < len(l):
        s = l[i]
        if s.t & FLAG_FINAL:
            result += "Final state : "+str(s) + "\r\n"
        elif s.t & FLAG_EPSILON:
            result += "State (Epsilon): "+str(s) + "\r\n"
            result += " Epsilon => " + str(s.next1) + "\r\n"
            if(s.next2):
                result += " Epsilon => " + str(s.next2) + "\r\n"
        elif s.t & FLAG_ANY:
            result += "State (Any): "+ str(s) + "\r\n"
            result += " Any => " + str(s.next1) + "\r\n"
        else:
            result += "State ("+chr(s.t)+") : "+ str(s) + "\r\n"
            result += " "+chr(s.t)+" => "+str(s.next1) + "\r\n"
        if not(s.next1 in l) and s.next1 != None:
            l.append(s.next1)
        if not(s.next2 in l) and s.next2 != None:
            l.append(s.next2)
        i += 1
    print result

if __name__=='__main__':
    print "Step By Step Regular expressions module by Michael Coquard :)"