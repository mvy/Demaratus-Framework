#!/usr/bin/python
# -*- coding: utf-8 -*-

from streamfilters import *
import stepregexp as re
import re as stdre
import tools
import string


REGEXP_URI = "(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?"
REGEXP_HTTP_REQUEST = "(GET|POST|PUT|DELETE|HEAD|TRACE|CONNECT|OPTIONS) "+REGEXP_URI+" HTTP/[0-9]\.[0-9]\r\n"
REGEXP_HTTP_RESPONSE = "HTTP/[0-9]\.[0-9] [1-5][0-1][0-9] [^\r\n]*\r\n"
REGEXP_HTTP_REQRESP = "("+REGEXP_HTTP_REQUEST+"|"+REGEXP_HTTP_RESPONSE+")"

class HTTPHeaderPermutFilterIn(AbstractTerminalFilterIn):
    """ Cache des caractères en permutant les headers d'une requête http. """
    def __init__(self,reader):
        AbstractTerminalFilterIn.__init__(self,reader)
        self.patternRequest = re.compile(REGEXP_HTTP_REQRESP)
        self.intoheader = False
        self.headers = []
        self.currentHeader = ""
        self.efficiency = 0
        self.requestline = ""
    def write(self,c):
        AbstractTerminalFilterIn.write(self,c)
        # on regarde si l'on se trouve dans les headers http
        self.buffer += c
        if self.intoheader:
            self.currentHeader += c
            # fin des headers, on calcule le nombre de caractères pouvant être
            # stéganographiés
            if self.buffer[-4:] == "\r\n\r\n":
                # on classe les headers par ordre alphabetiques, ceci servira de
                # référence
                self.headers.sort()
                # suppression des doublons (cas où deux headers seraient
                # identiques ce qui fausserait le codage)
                pred = None
                headers = []
                for h in self.headers:
                    if pred != h:
                        headers.append(h)
                        pred = h
                # calcul de l'efficacité
                n = tools.fact(len(self.headers))
                e = 0
                while n > 1:
                    n >>= 1
                    e += 1
                self.efficiency = e
                self.state = FILTER_PASS
                return self.state
            elif self.buffer[-2:] == "\r\n":
                # si l'on trouve une ligne de header, on l'ajoute à la liste
                self.headers.append(self.currentHeader)
                self.currentHeader = ""
            self.state = FILTER_WAITING
        # si ce n'est pas le cas, on cherche à détécter la première ligne d'une
        # requête http
        else:
            x = self.patternRequest.next(c)
            self.requestline += c
            if x == re.PASS:
                # reconnaissance partielle de la première ligne de requête
                self.state = FILTER_WAITING
            elif x == re.ACCEPT:
                # si la première ligne de requête est identifiée, le filtre
                # commence à enregistrer les entêtes
                self.intoheader = True
                self.state = FILTER_WAITING
            else:
                # si la première ligne n'est pas identifiée, on rejete le buffer
                self.state = FILTER_PASS
        return self.state
    def reset(self):
        AbstractTerminalFilterIn.reset(self)
        self.headers = []
        self.currentHeader = ""
        self.efficiency = 0
        self.intoheader = False
        self.patternRequest.reset()
        self.requestline = ""
    def read(self):
        AbstractTerminalFilterIn.read(self)
        if self.efficiency:
            n = self.reader.read(self.efficiency)
            # permutations des headers
            headers = tools.unrank(n,self.headers)
            return self.requestline + string.join(headers,"") + "\r\n"
        else:
            return self.buffer

class HTTPHeaderPermutFilterOut(AbstractTerminalFilterOut):
    """ Décode des caractères codés dans la permutation des entêtes http. """
    def __init__(self,writer):
        AbstractTerminalFilterOut.__init__(self,writer)
        self.patternRequest = re.compile(REGEXP_HTTP_REQRESP)
        self.intoheader = False
        self.headers = []
        self.currentHeader = ""
        self.efficiency = 0
        self.requestline = ""
    def write(self,c):
        AbstractTerminalFilterOut.write(self,c)
        self.buffer += c
        if self.intoheader:
            self.currentHeader += c
            if self.buffer[-4:] == "\r\n\r\n":
                n = tools.fact(len(self.headers))
                e = 0
                while n > 1:
                    n >>= 1
                    e += 1
                self.efficiency = e
                self.state = FILTER_PASS
                return self.state
            elif self.buffer[-2:] == "\r\n":
                self.headers.append(self.currentHeader)
                self.currentHeader = ""
            self.state = FILTER_WAITING
        else:
            x = self.patternRequest.next(c)
            self.requestline += c
            if x == re.PASS:
                self.state = FILTER_WAITING
            elif x == re.ACCEPT:
                self.intoheader = True
                self.state = FILTER_WAITING
            else:
                self.state = FILTER_PASS
        return self.state
    def reset(self):
        AbstractTerminalFilterOut.reset(self)
        self.headers = []
        self.currentHeader = ""
        self.efficiency = 0
        self.intoheader = False
        self.patternRequest.reset()
        self.requestline = ""
    def read(self):
        AbstractTerminalFilterOut.read(self)
        if self.efficiency:
            # décodage de la permutation
            n = tools.rank(self.headers)
            self.writer.write(n,self.efficiency)
            # REM : pas besoin de refaire les permutations inverses sur les
            # headers pour que le serveur web comprenne la requête !
        return self.buffer

class HTTPHeaderHostChanger(AbstractFilter):
    """ Filtre qui modifie le header 'Host' des requêtes HTTP. Il permet de
        modifier cette entête pour indiquer le véritable hôte plutôt que
        l'adresse du client du tunnel (lorsqu'un navigateur se connecte sur
        le client de tunnel)"""
    def __init__(self,host):
        """ Construit un filtre qui remplacera l'hôte par celui spécifié dans
            le filtre. """
        AbstractFilter.__init__(self)
        self.pattern = re.compile("Host: [^\r\n]+\r\n")
        self.found = False
        self.host = host
    def reset(self):
        AbstractFilter.reset(self)
        self.pattern.reset()
        self.found = False
    def write(self,c):
        AbstractFilter.write(self,c)
        self.buffer += c
        x = self.pattern.next(c)
        if x == re.FAIL:
            self.state = FILTER_PASS
            return self.state
        if x == re.PASS:
            self.state = FILTER_WAITING
            return self.state
        self.state = FILTER_PASS
        self.found = True
        return self.state
    def read(self):
        AbstractFilter.read(self)
        if self.found:
            return "Host: "+self.host+"\r\n"
        else:
            return self.buffer
        

REGEXP_HTML_SP = "([\n\r\t ]+)"
REGEXP_HTML_EQ = REGEXP_HTML_SP+"?="+REGEXP_HTML_SP+"?"
REGEXP_HTML_NAME = "[A-Za-z0-9:_][A-Za-z0-9._:-]*"
REGEXP_HTML_REF = "&(#[0-9]+|"+REGEXP_HTML_NAME+");"
REGEXP_HTML_VALUE = "(\"([^<&\"]|"+REGEXP_HTML_REF+")*\"|'([^<&\']|"+REGEXP_HTML_REF+")*')"
REGEXP_HTML_TAG = "<"+REGEXP_HTML_NAME+"("+REGEXP_HTML_SP+REGEXP_HTML_NAME+REGEXP_HTML_EQ+REGEXP_HTML_VALUE+")*"+REGEXP_HTML_SP+"?/?>"


class HTMLTagsPermutFilterIn(AbstractTerminalFilterIn):
    """ Cache des caractères en permutant les attributs des balises XML/HTML."""
    def __init__(self,reader):
        AbstractTerminalFilterIn.__init__(self,reader)
        self.pattern = re.compile(REGEXP_HTML_TAG)
        self.attribs = []
        self.start = ""
        self.end = ""
        self.efficiency = 0
    def write(self,c):
        AbstractTerminalFilterIn.write(self,c)
        self.buffer += c
        x = self.pattern.next(c)
        if x == re.PASS:
            self.state = FILTER_WAITING
        elif x == re.ACCEPT:
            # On parse la balise obtenue pour récupérer les attributs
            t = tools.XMLTagExtract(self.buffer)
            self.start = t[1]
            self.end = t[2]
            l = t[0]
            if l:
                # calcul de l'efficacité
                l.sort()
                # suppression des doublons...
                pred = None
                for h in l:
                    if pred != h:
                        self.attribs.append(h)
                        pred = h
                n = tools.fact(len(self.attribs))
                e = 0
                while n > 1:
                    n >>= 1
                    e += 1
                self.efficiency = e
            self.state = FILTER_PASS
        else:
            self.state = FILTER_PASS
        return self.state
    def reset(self):
        AbstractTerminalFilterIn.reset(self)
        self.pattern.reset()
        self.attribs = []
        self.start = ""
        self.end = ""
        self.efficiency = 0
    def read(self):
        AbstractTerminalFilterIn.read(self)
        if self.efficiency:
            n = self.reader.read(self.efficiency)
            # permutations des attributs
            attribs = tools.unrank(n,self.attribs)
            return self.start+" "+string.join(attribs," ")+" "+self.end
        else:
            return self.buffer

class HTMLTagsPermutFilterOut(AbstractTerminalFilterOut):
    """ Cache des caractères en permutant les attributs des balises XML/HTML."""
    def __init__(self,reader):
        AbstractTerminalFilterOut.__init__(self,reader)
        self.pattern = re.compile(REGEXP_HTML_TAG)
        self.attribs = []
        self.start = ""
        self.end = ""
        self.efficiency = 0
    def write(self,c):
        AbstractTerminalFilterOut.write(self,c)
        self.buffer += c
        x = self.pattern.next(c)
        if x == re.PASS:
            self.state = FILTER_WAITING
        elif x == re.ACCEPT:
            # On parse la balise obtenue pour récupérer les attributs
            t = tools.XMLTagExtract(self.buffer)
            self.start = t[1]
            self.end = t[2]
            self.attribs = t[0]
            if self.attribs:
                # calcul de l'efficacité
                n = tools.fact(len(self.attribs))
                e = 0
                while n > 1:
                    n >>= 1
                    e += 1
                self.efficiency = e
            self.state = FILTER_PASS
        else:
            self.state = FILTER_PASS
        return self.state
    def reset(self):
        AbstractTerminalFilterOut.reset(self)
        self.pattern.reset()
        self.attribs = []
        self.start = ""
        self.end = ""
        self.efficiency = 0
    def read(self):
        AbstractTerminalFilterOut.read(self)
        if self.efficiency:
            n = tools.rank(self.attribs)
            self.writer.write(n,self.efficiency)
        return self.buffer

class HTTPDataExtractorFilter(AbstractTerminalFilter):
    """ Ce filtre extrait la partie data d'une requête ou réponse HTTP, la
        forwarde à un filtre et réencapsule le résultat.
        chunksize spécifie la longueur des chunks que le filtre crée lorsqu'il
        doit réencoder une requête http utilisant un encodage par chunks. """
    def __init__(self,filter,newchunksize = 65535):
        AbstractTerminalFilter.__init__(self)
        self.filter = filter
        self.patternRequest = re.compile(REGEXP_HTTP_REQRESP)
        self.intoheader = False
        self.headers = []
        self.currentHeader = ""
        self.intodata = False
        self.length = 0
        self.requestline = ""
        self.data = ""
        self.finish = False
        # gestions des chunks
        self.bchunked = False
        self.chunklength = 0
        self.chunksizeline = ""
        self.endofchunk = 0
        self.endofrequest = False
        self.newchunksize = newchunksize
        # pour Content-Length
        self.blength = False
    def write(self,c):
        # fonctionnement similaire au filtre de permutation
        # pour la détéction du header
        AbstractTerminalFilter.write(self,c)
        self.buffer += c
        if self.intodata:
            #on récupère les données
            if self.bchunked:
                # détection de "\r\n" se trouvant après le chunk
                if self.endofchunk == 1:
                    if c != "\r":
                        self.state = FILTER_PASS
                        return self.state
                    self.endofchunk = 2
                elif self.endofchunk == 2:
                    if c != "\n":
                        self.state = FILTER_PASS
                        return self.state
                    self.endofchunk = 0
                # récupération des données du chunk
                elif self.chunklength:
                    self.chunklength -= 1
                    self.data += c
                    if not self.chunklength:
                        self.endofchunk = 1
                # lecture de la taille d'un chunk
                else:
                    self.chunksizeline += c
                    # on récupère la ligne contenant la taille du chunk
                    if self.chunksizeline[-2:] == "\r\n":
                        try:
                            self.chunklength = int(self.chunksizeline[:-2],16)
                        except Exception, ex:
                            self.state = FILTER_PASS
                            return self.state
                        self.chunksizeline = ""
                        if self.chunklength == 0:
                            self.finish = True
                            self.state = FILTER_PASS
            elif self.blength:
                if self.length > 0:
                    self.data += c
                    self.length -= 1
                    if self.length == 0:
                        self.finish = True
                        self.state = FILTER_PASS
                        return self.state
                else:
                    self.state = FILTER_PASS
                    return self.state
            else:
                # codage non supporté, on rejette le buffer
                # la longueur des données ne peut être déterminée !
                self.state = FILTER_PASS
        elif self.intoheader:
            self.currentHeader += c
            if self.buffer[-4:] == "\r\n\r\n":
                if self.blength or self.bchunked:
                    self.intodata = True
                else:
                    self.state = FILTER_PASS
                    return self.state
            elif self.buffer[-2:] == "\r\n":
                #on regarde si on a une entete Transfer-Encoding
                if self.currentHeader == "Transfer-Encoding: chunked\r\n":
                    self.bchunked = True
                #on regarde si on a une entête Content-Length
                if self.currentHeader[:15] == "Content-Length:":
                    try:
                        self.length = int(self.currentHeader[15:])
                    except:
                        self.state = FILTER_PASS
                        return self.state
                    if self.length > 0:
                        self.blength = True
                self.headers.append(self.currentHeader)
                self.currentHeader = ""
            self.state = FILTER_WAITING
        else:
            x = self.patternRequest.next(c)
            self.requestline += c
            if x == re.PASS:
                self.state = FILTER_WAITING
            elif x == re.ACCEPT:
                self.intoheader = True
                self.state = FILTER_WAITING
            else:
                self.state = FILTER_PASS
        return self.state
    def reset(self):
        AbstractTerminalFilter.reset(self)
        self.patternRequest.reset()
        self.intoheader = False
        self.headers = []
        self.currentHeader = ""
        self.intodata = False
        self.length = 0
        self.requestline = ""
        self.data = ""
        self.finish = False
        self.bchunked = False
        self.chunklength = 0
        self.chunksizeline = ""
        self.endofchunk = 0
        self.endofrequest = False
        self.blength = False
    def read(self):
        AbstractTerminalFilter.read(self)
        if self.finish:
            if self.bchunked:
                # passage des données dans le filtre
                buffer = ""
                for c in self.data:
                    x = self.filter.write(c)
                    if x == FILTER_PASS:
                        buffer += self.filter.read()
                        self.filter.reset()
                if x == FILTER_PASS:
                    # découpage en chunks
                    self.buffer = self.requestline+string.join(self.headers,"")+"\r\n"
                    j = 0
                    last = False
                    l = len(buffer)
                    i = 0
                    # premier chunk
                    while j < l:
                        if (l-j) < self.newchunksize:
                            self.buffer += tools.intToHex(l-j)+"\r\n"
                            i += l-j
                        else:
                            self.buffer += tools.intToHex(self.newchunksize)+"\r\n"
                            i += self.newchunksize
                        while j < i:
                            self.buffer += buffer[j]
                            j += 1
                        self.buffer += "\r\n"
                    if j == l:
                        self.buffer += "0\r\n"
                else:
                    raise FilterException("HTTPDataExtractorFilter is blocked indefinitely because its internal filter has blocked")
            elif self.blength:
                self.buffer = ""
                for c in self.data:
                    # envoi des données dans le filtre
                    x = self.filter.write(c)
                    if x == FILTER_PASS:
                        self.buffer += self.filter.read()
                        self.filter.reset()
                if self.length == 0:
                    # dernier octet, on regarde si le filtre interne est
                    # passant sinon on envoie une exception
                    if x == FILTER_PASS:
                        # si oui, on reconstruit la requête
                        # modification de la longueur des données
                        for i in range(len(self.headers)):
                            if self.headers[i][:15] == "Content-Length:":
                                self.headers[i] = "Content-Length: "+str(len(self.buffer))+"\r\n"
                        self.buffer = self.requestline+string.join(self.headers,"")+"\r\n"+self.buffer
                    else:
                        raise FilterException("HTTPDataExtractorFilter is blocked indefinitely because its internal filter has blocked")
            else:
                raise FilterException("HTTPDataExtractorFilter cannot determinate encoding method to encode stream un read() method.")
        return self.buffer

###s = "GET / HTTP/1.1\r\nHost: truc\r\nContent-Length: 82\r\n\r\n<html reg='lol' test='machin' r='14' v='14' v='154' v='614' v='145' yu='4' uy='4'>"
##s = "GET / HTTP/1.1\r\nHost: truc\r\nContent-Length: 82\r\nTransfer-Encoding: chunked\r\n\r\n32\r\n<html reg='lol' test='machin' r='14' v='14' v='154\r\n20\r\n' v='614' v='145' yu='4' uy='4'>\r\n0\r\nertert"
###s = "GET / HTTP/1.1\r\nHost: truc\r\nContent-Length: 82\r\nTransfer-Encoding: chunked\r\n\r\n53\r\n<html reg='lol' v='14' v='614' v='145' v='154' yu='4' test='machin' uy='4' r='14' >\r\nertert"
##s = "GET / HTTP/1.1\r\nHost: truc\r\nContent-Length: 0\r\n\r\n"
##m = ""
##
##fin = HTTPDataExtractorFilter(HTMLTagsPermutFilterIn(BinaryReader(PacketReader(FIFOBuffer("test")))))
####fou = HTTPDataExtractorFilter(HTMLTagsPermutFilterOut(BinaryWriter(PacketWriter(StdOutWriter()))))
##
##for i in s:
##    x = fin.write(i)
##    if x == FILTER_PASS:
##        m += fin.read()
##        fin.reset()
##
##print repr(m)
##print x
##s = ""
##for i in m:
##    x = fou.write(i)
##    if x == FILTER_PASS:
##        s += fou.read()
##        fou.reset()
##print x
##print repr(s)

