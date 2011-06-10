#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import threading
import random

from tools import *

""" Classes pour manipuler des filtres sur des flux de données. """

FILTER_EMPTY = 0
""" Etat vide : le filtre se trouve soit dans son état initial soit on ne
    lui a pas encore injecté de caractère depuis sa dernière lecture. Le
    filtre ne doit pas contenir de caractères du flux lorsqu'il se trouve
    dans cet état. """
FILTER_PASS = 1
""" Etat passant : le filtre a effectué un traitement et des caractères sont
    disponibles dans son buffer de sortie. Le filtre doit être lu avant d'
    écrire de nouveaux caractères. """
FILTER_WAITING = 2
""" Etat d'attente : le filtre a reconnu un modèle partiellement mais pas
    totalement (il attend encore des caractères). """
FILTER_FLUSHED = 3
""" Etat final : le filtre a renvoyé ses donnés et doit être remis à zero
    avant d'effectuer une nouvelle opération. """

class FilterException(Exception):
    """ Exceptions générées par les filtres """
    def __init__(self,message):
        Exception.__init__(self,message)

""" Nombre maximal d'octets qu'un filtre peut retenir (pour éviter qu'un bloquage ne sature la mémoire). """
MAX_SIZE_BUFFER = 1000000 # environ 1 Mo....


class AbstractFilter:
    """ Classe abstraite représentant un filtre de transformation """
    def __init__(self):
        """ Construit un nouveau filtre. Ce constructeur est utilisé par les
            classes héritées. """
        self.state = FILTER_EMPTY
        self.buffer = ""
        self.buffsize = 0
    def write(self,c):
        """ Ecrit un caractère dans le filtre. Cette fonction retourne l'état du
            filtre après le traitement du caractère. Une exception est générée
            si le filtre doit être lu avant d'écrire un caractère (son état
            courant est pass ou accept). """
        if self.state == FILTER_FLUSHED:
            raise FilterException("Filter must be reset")
        if self.state == FILTER_PASS:
            raise FilterException("Filter is in pass state and must be read")
        if self.buffsize == MAX_SIZE_BUFFER:
            raise FilterException("Filter is full")
        self.buffsize += 1
    def read(self):
        """ Cette fonction retourne les caractères traités par le filtre. Un
            filtre vide ne peut pas être lu, dans le cas contraire, une
            exception est retournée. Cette règle est valable aussi pour un
            filtre en attente. """
        if self.state == FILTER_EMPTY:
            raise FilterException("Empty filter cannot be read")
        if self.state == FILTER_WAITING:
            raise FilterException("Waiting filter cannot be read")
        self.state = FILTER_FLUSHED
    def reset(self):
        """ Remet à zéro le filtre, son buffer est vidé et son état interne est
            remis tel qu'il était à la création du filtre. """
        self.state = FILTER_EMPTY
        self.buffer = ""
        self.buffsize = 0
    
class AbstractFilterGroup(AbstractFilter):
    """ Classe abstraite représentant un groupe de filtres devant être traités
        de manière cohérente. """
    def __init__(self,filters=[]):
        """ Construit un nouveau groupe de filtres à l'aide d'une liste de
            filtres. Cette liste peut être vide (par défaut). """
        AbstractFilter.__init__(self)
        self.filters = filters
        self.filters_number = len(self.filters)
    def reset(self):
        """ Remet à zero le groupe de filtre et tous ses filtres internes. """
        AbstractFilter.reset(self)
        for f in self.filters:
            f.reset()

class AbstractTerminalFilter(AbstractFilter):
    """ Classe abstraite pour les filtres terminaux. Les filtres terminaux sont
        ceux qui exécutent les traitements stéganographiques sur le flux. Ils
        utilisent flux de paquets (jeu de caractères ASCII étendus)
        qu'ils doivent coder ou décoder suivant leur type (in ou out) """

class AbstractTerminalFilterIn(AbstractTerminalFilter):
    """ Classe abstraite pour les filtres terminaux d'entrée, c'est à dire les
        filtres qui encodent des paquets dans le flux. """
    def __init__(self,reader):
        AbstractTerminalFilter.__init__(self)
        self.reader = reader

class AbstractTerminalFilterOut(AbstractTerminalFilter):
    """ Classe abstraite pour les filtres terminaux de sortie, c'est à dire les
        filtres qui décodent des paquets du flux. """
    def __init__(self,writer):
        AbstractTerminalFilter.__init__(self)
        self.writer = writer

class SerialFilterGroup(AbstractFilterGroup):
    """ Groupe de filtres dont le traitement doit être effectué en série. """
    def __init__(self,filters=[]):
        """ Construit un nouveau groupe de filtres à l'aide d'une liste de
            filtre. Cette liste peut être vide (par défaut). """
        AbstractFilterGroup.__init__(self,filters)
    def write(self,c):
        """ Ecrit un caractère à l'entrée du groupe de filtres série et retourne
            l'état du groupe. L'état du groupe de filtres sera passant si tous
            ses filtres le sont aussi. Si un seul filtre est en cours de
            traitement (FILTER_WAITING), le groupe sera aussi considéré en cours
            de traitement (on doit attendre la fin du traitement). """
        AbstractFilterGroup.write(self,c)
        #sys.stdout.write(c)
        buffer_in = c
        buffer_out = ""
        for i in range(self.filters_number):
            for x in buffer_in:
                # si le filtre est passant, on transfert le buffer dans le
                # filtre suivant
                if self.filters[i].write(x) == FILTER_PASS:
                    buffer_out += self.filters[i].read()
                    # on fait un reset sur le filtre
                    self.filters[i].reset()
            buffer_in = buffer_out
            buffer_out = ""
        # On copie le dernier buffer dans le buffer du filtre
        self.buffer += buffer_in
        # Calcul de l'état final (le filtre est en état d'attente ssi un de
        # ses filtre l'est)
        self.state = FILTER_PASS
        for f in self.filters:
            if f.state == FILTER_WAITING:
                self.state = FILTER_WAITING
                return self.state
        return self.state
    def read(self):
        """ Lit le buffer résultat du groupe de filtres """
        AbstractFilterGroup.read(self)
        return self.buffer

class NullTerminalFilter(AbstractTerminalFilter):
    """ Filtre toujours passant et qui ne fait aucun traitement."""
    def __init__(self):
        AbstractTerminalFilter.__init__(self)
    def write(self,c):
        AbstractTerminalFilter.write(self,c)
        self.buffer += c
        self.state = FILTER_PASS
        return self.state
    def read(self):
        AbstractTerminalFilter.read(self)
        return self.buffer

# manipulation des flux d'octets

class AbstractReader:
    """ Classe abstraite permettant de lire un flux d'octets (=carcatères). """
    def read(self,n):
        """ Lit une chaîne de caractères de la file d'au maximum la taille
            spécifiée. """
        return ""
        
class AbstractWriter:
    """ Classe abstraite permettant d'écrire un flux d'octets. """
    def write(self,c):
        """ Ecrit le caractère c dans le flux. """
        return None

class StdOutWriter(AbstractWriter):
    """ Permet d'écrire un flux d'octets dans la sortie standard. """
    def write(self,c):
        """ Ecrit le caractère c dans la sortie standard. """
        sys.stdout.write(c)

class FIFOBuffer(AbstractReader,AbstractWriter):
    """ Buffer de type FIFO permettant de lire et d'écrire des caractères
        (octets), la capacité de ce buffer s'ajuste autoamtiquement. """
    def __init__(self,s=""):
        """ Crée un nouveau buffer de caractères à l'aide d'une chaîne. Par
            défaut, le buffer sera vide. """
        self.buffer = s
    def read(self,n):
        """ Lit une chaîne de caractères de la file d'au maximum la taille
            spécifiée. """
        if n == 0:
            return ""
        s = self.buffer[:n]
        self.buffer = self.buffer[n:]
        return s
    def write(self,c):
        """ Ajoute un caractère ou une chaîne dans la file. """
        if c:
            self.buffer += c
    def sizeOfData(self):
        """ Retourne le nombre de caractères (octets) dans le buffer. """
        return len(self.buffer)
    def getBuffer(self):
        """ Retourne le contenu actuel du buffer. """
        return self.buffer

class SynchronizedFIFOBuffer(FIFOBuffer):
    """ Buffer fifo pouvant fonctionner de manière asynchrone avec l'utilisation
        de threads. Les méthodes read et write sont protégées par mutex. """
    def __init__(self,s=""):
        FIFOBuffer.__init__(self,s)
        self.lock = threading.Lock()
    def read(self,n):
        self.lock.acquire()
        s = FIFOBuffer.read(self,n)
        self.lock.release()
        return s
    def write(self,c):
        self.lock.acquire()
        FIFOBuffer.write(self,c)
        self.lock.release()
    def sizeOfData(self):
        self.lock.acquire()
        x = FIFOBuffer.sizeOfData(self)
        self.lock.release()
        return x
    def getBuffer(self):
        self.lock.acquire()
        b = FIFOBuffer.getBuffer(self)
        self.lock.release()
        return b


class PipeWriter(AbstractWriter):
    """ Permet d'écrire un flux d'octets dans un tube quelconque. """
    def __init__(self,pipe):
        """ Construit un nouveau pipe writer à partir du tube donné en
            paramètre. """
        self.pipe = pipe
    def write(self,c):
        """ Ecrit le caractère ou la chaîne c dans le tube. """
        if c:
            self.pipe.write(c)

# Classes pour la gestion du protocole de jeu de caractères étandus (sur 9 bits)


PACKET_EMPTY = 0x100
PACKET_CHAR_MASK = 0x0ff
PACKET_SIZE = 9
PACKET_MASK = 0x1ff

class PacketReader:
    """ Encapsule un caractère ASCII (8bits) dans un entier de 9 bits (paquet).
        Ceci permet d'insérer des codes particuliers :
        0x000 à 0x0ff désigne un caractère ASCII bits
        0x100 désigne un caractère 'vide'. """
    def __init__(self,reader):
        """ Nouvelle instance d'un packet reader à l'aide d'un objet de type
            reader fournissant un flux de caractères 8 bits. """
        self.reader = reader
    def read(self,n):
        """ Lit n paquets de 9 bits sur le flux. Si l'objet de type reader
            attaché ne peut fournir autant de caractères 8 bits, des
            paquets codant des caractères vides seront ajoutés. """
        buffer = self.reader.read(n)
        result = []
        for c in buffer:
            result.append(ord(c))
        for _ in range(n - len(result)):
            result.append(PACKET_EMPTY)
        return result

class PacketWriter:
    """ Décode les paquets générés par un packet reader et écrit le flux de
        caractères correspondant dans un objet de type writer. """
    def __init__(self,writer):
        """ Nouvelle instance d'un packet writer à l'aide d'un objet de type
            writer. """
        self.writer = writer
    def write(self,p):
        """ Ecrit une chaîne de paquets dans le flux. """
        buffer = ""
        for c in p:
            if not (c & PACKET_EMPTY):
                buffer += chr(c)
        self.writer.write(buffer)

# Classes pour la gestion de la couche "physique" binaire du flux stéganographié

class BinaryReader:
    """ Lecture bit à bit d'un flux de paquets provenant d'un packet reader. """
    def __init__(self,packetreader):
        self.packetreader = packetreader
        self.last = 0
        self.remain = 0
    def read(self,n):
        """ Lecture de n bits du flux. Les n bits sont renvoyés dans un nombre
            entier. Le bit de poids fort sera le premier bit lu. Le second bit
            lu sera celui de poids plus faible etc..."""
        result = 0
        # on regarde s'il reste des bits à lire dans le buffer local
        if self.remain:
            if self.remain >= n:
                result = self.last >> (self.remain - n)
                self.last &= ((1 << (self.remain - n)) - 1)
                self.remain -= n
                return result
            else:
                result = self.last
                n -= self.remain
        # nombre de paquets de 9 bits à lire
        nb,r = divmod(n,PACKET_SIZE)
        if nb:
            packets = self.packetreader.read(nb)
            for p in packets:
                result <<= PACKET_SIZE
                result |= p
                n -= PACKET_SIZE
            self.remain = 0
        if r:
            self.last = self.packetreader.read(1)[0]
            # traitment du dernier paquet incomplet (si c'est le cas)
            result <<= r
            result |= (self.last >> (PACKET_SIZE - r))
            self.last &= ((1 << (PACKET_SIZE - n)) - 1)
            self.remain = PACKET_SIZE - r
        return result
    def reset(self):
        """ Remet à zéro le binary reader. Les bits stockés dans l'instance
            seront perdus. """
        self.last = 0
        self.remain = 0
        
class BinaryWriter:
    """ Ecriture bit à bit d'un flux de paquets vers un packet writer. """
    def __init__(self,packetwriter):
        self.current = 0
        self.remain = 0
        self.packetwriter = packetwriter
    def write(self,n,m):
        """ Ecrit m bits de données issus de l'entier n. (m correspond aux
            nombre de bits à partir du bit de poids faible). """
        l = []
        r = PACKET_SIZE - self.remain
        if r > m:
            # on ne peut pas compléter un paquet entier mais on ajoute
            # les bits au buffer interne
            self.current <<= m
            self.current |= n
            self.remain += m
            return
        # on peut compléter un paquet entier
        m -= r
        self.current <<= r
        self.current |= ((n >> m) & ((1 << r) - 1))
        l.append(self.current)
        self.remain = 0
        while m >= PACKET_SIZE:
            m -= PACKET_SIZE
            l.append((n >> m) & PACKET_MASK)
        self.packetwriter.write(l)
        # calcul des bits restants
        self.remain = m
        self.current = n & ((1 << m) - 1)
        return
    def reset(self):
        """ Remet à zéro le binary writer. Les bits stockés dans l'instance
            seront perdus. """
        self.current = 0
        self.remain = 0


class BinaryTransactionReader:
    """ Permet de stocker des transactions de flux binaires similaires aux
        transactions de bases de données. Il est possible de faire un commit()
        pour confirmer que le flux a été transmis ou un rollback pour
        restaurer le flux en cas de problème. """
    def __init__(self,binaryreader):
        """ Initialise un nouvel objet à l'aide d'un binary reader."""
        self.buffer = 0
        self.nbuffer = 0
        self.binaryreader = binaryreader
        self.pos = 0
    def read(self,n):
        if (self.pos + n) > self.nbuffer:
            # pas assez de données, on en redemande au binary reader
            nb = self.pos + n - self.nbuffer
            x = self.binaryreader.read(nb)
            self.buffer <<= nb
            self.buffer |= x
            self.nbuffer = n + self.pos
        result = ((1 << n) - 1) & (self.buffer >> (self.nbuffer - self.pos - n))
        self.pos += n
        return result
    def commit(self):
        self.buffer = 0
        self.nbuffer = 0
        self.pos = 0
    def rollback(self):
        self.pos = 0

class BinaryTransactionWriter:
    """ Permet de stocker des transactions de flux binaire en écriture. Ceci
        permet de confirmer l'écriture d'un flux par un commit() ou d'annuler
        l'écriture par un rollback. """
    def __init__(self,binarywriter):
        """ Initialise un nouvel objet à l'aide d'un binary writer."""
        self.buffer = 0
        self.n = 0
        self.binarywriter = binarywriter
    def write(self,n,m):
        x = n & ((1 << m) - 1)
        self.buffer <<= m
        self.buffer |= x
        self.n += m
    def commit(self):
        self.binarywriter.write(self.buffer,self.n)
        self.buffer = 0
        self.n = 0
    def rollback(self):
        self.buffer = 0
        self.n = 0


class BinaryAuthenticateReader:
    """ Permet d'envoyer le code d'authentification du flux """
    def __init__(self,binaryreader,password):
        """ Nouvelle instance construite avec un binary reader et un mot de
            passe qui sera envoyé pour l'authentification."""
        self.binaryreader = binaryreader
        # conversion du mot de passe en binaire
        x = 0
        for c in password:
            x <<= 8
            x |= ord(c)
        self.password = x
        self.npassword = len(password)*8
        # REM : on suppose que len() renvoie une longueur en octets et non en
        # caractères (attention UTF-8 !!)
        self.currentpassword = self.password
        self.ncurrentpassword = self.npassword
        self.authenticated = False
    def read(self,n):
        """ Lit n bits du flux. Le mot de passe est d'abord lu en entier.
            suivi des données utiles."""
        # si on est authentifié, on envoi les données utiles
        if self.authenticated:
            return self.binaryreader.read(n)
        # sinon, on insert le mot de passe
        if n <= self.ncurrentpassword:
            self.ncurrentpassword -= n
            result = self.currentpassword >> self.ncurrentpassword
            self.currentpassword &= ((1 << self.ncurrentpassword) - 1)
            return result
        # lecture du reste du mot de passe
        result = self.currentpassword
        x = self.binaryreader.read(n - self.ncurrentpassword)
        result <<= (n - self.ncurrentpassword)
        result |= x
        self.authenticated = True
        return result
    def reset(self):
        """ Remise à zéro, le mot de passe sera de nouveau inséré aux prochains
            appels de la méthode read(). """
        self.authenticated = False
        self.currentpassword = self.password
        self.ncurrentpassword = self.npassword
        
class BinaryAuthenticateWriter:
    """ Vérifie si un code d'authentification est valide et transmet le flux
        de données utiles si c'est le cas. """
    AUTHENTICATED = 0
    FAILED = 1
    WAITING = 2
    def __init__(self,binarywriter,password,callback=None,nofail=False):
        """ Nouvelle instance construite avec un binary writer et un mot de
            passe qui permettra d'authentifier le flux entrant.
            password représente la chaîne d'initialisation attendue
            si nofail vaut True, l'authentification n'échoura jamais. Dans le
            cas contraire, si l'authentification échoue, il sera nécessaire
            d'appeler la méthode reset() avant de pouvoir se réauthentifier avec
            le bonne chaîne.
            callback permet de définir une fonction avec un paramètre booléen
            qui sera appelée dès que l'authentification aura réussie (paramètre
            à True) ou échouée (paramètre à False). """
        self.binarywriter = binarywriter
        x = 0
        for c in password:
            x <<= 8
            x |= ord(c)
        self.password = x
        self.npassword = len(password)*8
        self.currentpassword = self.password
        self.ncurrentpassword = self.npassword
        self.state = self.WAITING
        self.nofail = nofail
        self.callback = callback
    def write(self,n,m):
        """ Authentifie le flux à l'aide du mot de passe. Si l'authentification
            réussie, cette méthode ecrit le flux de données utiles dans le
            binary writer de l'instance. Tant que l'authentification n'est
            pas effectuée ou qu'elle a échouée, aucune donnée utile n'est
            transmise. """
        if self.state == self.AUTHENTICATED:
            self.binarywriter.write(n,m)
        elif self.state == self.WAITING:
            if m <= self.ncurrentpassword:
                if (self.currentpassword >> (self.ncurrentpassword - m)) != (n & ((1 << m) - 1)):
                    if self.nofail:
                        self.reset()
                    else:
                        self.state = self.FAILED
                        if self.callback != None:
                            self.callback(False)
                    return
                if m == self.ncurrentpassword:
                    self.state = self.AUTHENTICATED
                    if self.callback != None:
                        self.callback(True)
                    return
                self.ncurrentpassword -= m
                self.currentpassword &= ((1 << self.ncurrentpassword) - 1)
                return
            if (n >> (m - self.ncurrentpassword)) != self.currentpassword:
                self.state = self.FAILED
                if self.nofail:
                    self.reset()
                else:
                    self.state = self.FAILED
                    if self.callback != None:
                        self.callback(False)
                return
            self.state = self.AUTHENTICATED
            if self.callback != None:
                self.callback(True)
            self.binarywriter.write(n & ((1 << (m - self.ncurrentpassword)) - 1),m - self.ncurrentpassword)
    def reset(self):
        self.state = self.WAITING
        self.currentpassword = self.password
        self.ncurrentpassword = self.npassword


class BinaryOnOffReader:
    """ Transmet ou non un flux binaire en fonction de son état.
        La méthode setEnable() permet d'activer ou non le flux.
        Lorsque le flux est inactif (par défaut), la méthode read() renverra des
        données aléatoires ou que des bits à 0. """
    def __init__(self,binaryreader,randomdata = False):
        """ si randomdata vaut True, les bits renvoyés seront aléatoires. Sinon
            ils vaudront tous 0. """
        self.binaryreader = binaryreader
        self.enable = False
        self.random = randomdata
    def setEnable(self,b):
        self.enable = b
    def read(self,n):
        if self.enable:
            return self.binaryreader.read(n)
        if self.random:
            return random.getrandbits(n)
        return 0
