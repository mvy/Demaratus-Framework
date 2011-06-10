#!/usr/bin/python
# -*- coding: utf-8 -*-


from customfilters import *

import time
import socket
import threading
import sys
import select
import signal
import subprocess

class SocketThread(threading.Thread):
    """ Une thread qui s'occupe des opérations I/O sur les deux sockets du
        client et du serveur. """
    def __init__(self,listensock,remotehost,remoteport,filterin,filterout,verb,connectEvent,sendEvent,filterEvent):
        """ listensock correspond à la socket d'écoute qui reçoit les connexions
            externes, soit du client TCP, soit du client de tunnel."""
        threading.Thread.__init__(self)
        self.filterout = filterout
        self.filterin = filterin
        self.listensock = listensock
        self.remotehost = remotehost
        self.remoteport = remoteport
        self.event = threading.Event()
        self.verb = verb
        self.connectEvent = connectEvent
        self.sendEvent = sendEvent
        self.filterEvent = filterEvent
    def run(self):
        try:
            try:
                while(not self.event.isSet()):
                    # attente d'une connexion sur la socket d'écoute
                    sockout = None
                    # select avec un timeout de 1 seconde
                    listensocks,_,_ = select.select([self.listensock],[],[],1)
                    for listensock in listensocks:
                        sockin,(inaddr,inport) = listensock.accept()
                        if self.verb : print >> sys.stderr, "Receving connection from : %s:%s" % (inaddr,inport)
                        try:
                            try:
                                # ouverture de la socket cliente
                                remote = (self.remotehost,self.remoteport)
                                if self.verb : print >> sys.stderr, "Opening connection to : %s:%s" % remote
                                sockout = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                                sockout.connect(remote)
                                # attente des données sur l'une ou l'autre des sockets...
                                sockinclosed = False
                                sockoutclosed = False
                                while (not self.event.isSet()):
                                    # liste des sockets encore ouvertes
                                    sockopened = []
                                    if not sockinclosed:
                                        sockopened.append(sockin)
                                    if not sockoutclosed:
                                        sockopened.append(sockout)
                                    # test des sockets prêtes à lire
                                    socks,_,_ = select.select(sockopened,[],[],1)
                                    for sock in socks:
                                        # Traitement IN => OUT
                                        if sock == sockin:
                                            try:
                                                data = sockin.recv(4096)
                                            except:
                                                data = ""
                                            if not data:
                                                if self.verb : print >> sys.stderr, "Connection closed by client"
                                                sockinclosed = True
                                                sockin.close()
                                                # on stoppe l'envoi de données dans l'autre socket
                                                if not sockoutclosed:
                                                    sockout.shutdown(socket.SHUT_WR)
                                            else:
                                                try:
                                                    fdata = ""
                                                    for c in data:
                                                        # filtre passant
                                                        x = self.filterin.write(c)
                                                        if x == FILTER_PASS:
                                                            fdata = self.filterin.read()
                                                            self.filterEvent(True)
                                                            self.filterin.reset()
                                                            if not sockoutclosed:
                                                                i = 0
                                                                l = len(fdata)
                                                                while i < l:
                                                                    i += sockout.send(fdata[i:])
                                                                # un bloc à été envoyé avec succès, on envoi donc un événement
                                                                self.sendEvent(True)
                                                        # filtre en attente (on ne fait rien)
                                                except:
                                                    if not sockoutclosed:
                                                        sockout.shutdown(socket.SHUT_WR)
                                        # Traitement OUT => IN
                                        if sock == sockout:
                                            # idem pour l'autre sens...
                                            try:
                                                data = sockout.recv(4096)
                                            except:
                                                data = ""
                                            if not data:
                                                if self.verb : print >> sys.stderr, "Connection closed by server"
                                                sockoutclosed = True
                                                sockout.close()
                                                if not sockinclosed:
                                                    sockin.shutdown(socket.SHUT_WR)
                                            else:
                                                try:
                                                    fdata = ""
                                                    for c in data:
                                                        x = self.filterout.write(c)
                                                        if x == FILTER_PASS:
                                                            fdata = self.filterout.read()
                                                            self.filterEvent(False)
                                                            self.filterout.reset()
                                                            if not sockinclosed:
                                                                i = 0
                                                                l = len(fdata)
                                                                while i < l:
                                                                    i += sockin.send(fdata[i:])
                                                                self.sendEvent(False)
                                                except:
                                                    if not sockinclosed:
                                                        sockin.shutdown(socket.SHUT_WR)
                                    # si les deux sockets sont fermées on quitte la boucle
                                    if sockinclosed and sockoutclosed:
                                        break
                            except Exception, ex:
                                if self.verb : print >> sys.stderr, "Cannot connect to the remote host : %s " % ex
                        finally:
                            if sockin != None:
                                sockin.close()
                            if sockout != None:
                                sockout.close()
                            self.connectEvent()
            except Exception, ex:
                    if self.verb : print >> sys.stderr, "Accept() failed : %s " % ex
        finally:
            if self.verb : print >> sys.stderr, "Listening socket closed"
            if self.listensock != None:
                self.listensock.close()
    def stop(self):
        self.event.set()

# rattrapage des signaux
def sigHandler(signum, frame):
    print >> sys.stderr, "\r\nCtrl-C : Exiting..."

def client(bindhost,bindport,remotehost,remoteport,verb,command,password):
    if verb : print >> sys.stderr, "Starting TCPSteg client..."
    # redirection des signaux vers le handler
    signal.signal(signal.SIGINT,sigHandler)
    sock = None
    thread = None
    try:
        try:
            if verb : print >> sys.stderr, "Opening server socket on : %s:%s..." % (bindhost,bindport)
            sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sock.bind((bindhost,bindport))
            sock.listen(1)
            # préparation de la thread d'écoute
            fifo = SynchronizedFIFOBuffer()
            # ouverture du processus fils éventuel
            if command != None:
                cmdline = command.split()
                process = subprocess.Popen(cmdline,stdout=subprocess.PIPE,stdin=subprocess.PIPE,stderr=subprocess.STDOUT)
                pipeout = process.stdout
                pipein = process.stdin
            else:
                process = None
                pipeout = sys.stdin
                pipein = sys.stdout
            # les filtres d'entrée et de sortie
            # encodage des données
            transacin = BinaryTransactionReader(BinaryReader(PacketReader(fifo)))
            authentin = BinaryAuthenticateReader(transacin,password)
            filterin = HTTPHeaderPermutFilterIn(authentin)
            # décodage des données
            transacout = BinaryTransactionWriter(BinaryWriter(PacketWriter(PipeWriter(pipein))))
            authentout = BinaryAuthenticateWriter(transacout,password,nofail=True)
            filterout = SerialFilterGroup([HTTPDataExtractorFilter(HTMLTagsPermutFilterOut(authentout)),HTTPHeaderPermutFilterOut(authentout)])
            # on définit une fonction qui s'occupe de toute remetre à zéro lorsque la
            # connexion TCP est coupée
            def globalReset():
                authentin.reset()
                authentout.reset()
                # les filtres sont vidés de tous leurs caractères restants
                filterin.reset()
                filterout.reset()
                # les transactions en cours sont annulées (ce qui permet de
                # réenvoyer correctement les caractères n'ayant pas pu être
                # stéganographiés
                transacin.rollback()
                transacout.rollback()
            # idem pour commiter les caractères ayant été stéganographiés
            # et envoyés correctement
            def commitReadEvent(b):
                if b:
                    transacin.commit()
            def commitWriteEvent(b):
                if not b:
                    transacout.commit()
            thread = SocketThread(sock,remotehost,remoteport,filterin,filterout,verb,globalReset,commitReadEvent,commitWriteEvent)
            if verb : print >> sys.stderr, "Starting listening thread..."
            thread.start()
            # boucle d'attente sur stdin
            while True:
                # lecture caractère par caractère (non bufferisée) pour éviter
                # les bloquages
                data = pipeout.read(1)
                # si aucune donnée n'a été lue, la fonction read() a forcément
                # été interrompue (pas un signal), dans ce cas on quitte la boucle
                if not data:
                    break
                fifo.write(data)
            thread.stop()
            # on attend que la thread se termine avant de quitter le programme
            thread.join()
            if process != None:
                code = process.poll()
                if verb and code != None : print >> sys.stderr, "Child process terminated with code : %d" % code
            if verb : print >> sys.stderr, "Client closed !"
        except Exception, ex:
            if verb : print >> sys.stderr, "Error with socket : %s " % ex
    finally:
        if sock != None:
            sock.close()


def server(bindhost,bindport,remotehost,remoteport,verb,command,password):
    # REM : le code du serveur est quasi identique à celui du client. Cela vient
    # de la nature symétrique du tunnel. Les principaux changements sont les
    # filtres
    if verb : print >> sys.stderr, "Starting TCPSteg server..."
    signal.signal(signal.SIGINT,sigHandler)
    sock = None
    socketthread = None
    readthread = None
    try:
        try:
            if verb : print >> sys.stderr, "Opening server socket on : %s:%s..." % (bindhost,bindport)
            sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sock.bind((bindhost,bindport))
            sock.listen(1)
            fifo = SynchronizedFIFOBuffer()
            if command != None:
                cmdline = command.split()
                process = subprocess.Popen(cmdline,stdout=subprocess.PIPE,stdin=subprocess.PIPE,stderr=subprocess.STDOUT)
                pipeout = process.stdout
                pipein = process.stdin
            else:
                process = None
                pipeout = sys.stdin
                pipein = sys.stdout
            # on utilise les filtres réciproques de ceux du client...
            # encodage des données
            transacin = BinaryTransactionReader(BinaryReader(PacketReader(fifo)))
            authentin = BinaryAuthenticateReader(transacin,password)
            onoffin = BinaryOnOffReader(authentin)
            filterin = SerialFilterGroup([HTTPDataExtractorFilter(HTMLTagsPermutFilterIn(onoffin)),HTTPHeaderPermutFilterIn(onoffin)])
            # décodage des données
            transacout = BinaryTransactionWriter(BinaryWriter(PacketWriter(PipeWriter(pipein))))
            authentout = BinaryAuthenticateWriter(transacout,password,onoffin.setEnable)
            filterout = SerialFilterGroup([HTTPHeaderPermutFilterOut(authentout),HTTPHeaderHostChanger(remotehost+":"+str(remoteport))])
            def globalReset():
                authentin.reset()
                authentout.reset()
                filterin.reset()
                filterout.reset()
                transacin.rollback()
                transacout.rollback()
            def commitReadEvent(b):
                if not b:
                    transacin.commit()
            def commitWriteEvent(b):
                if b:
                    transacout.commit()
            thread = SocketThread(sock,remotehost,remoteport,filterout,filterin,verb,globalReset,commitReadEvent,commitWriteEvent)
            if verb : print >> sys.stderr, "Starting listening thread..."
            thread.start()
            while True:
                data = pipeout.read(1)
                if not data:
                    break
                fifo.write(data)
            thread.stop()
            thread.join()
            if process != None:
                code = process.poll()
                if verb and code != None : print >> sys.stderr, "Child process terminated with code : %d" % code
            if verb : print >> sys.stderr, "Server closed !"
        except Exception, ex:
            if verb : print >> sys.stderr, "Error with socket : %s " % ex
    finally:
        if sock != None:
            sock.close()

#-------------------------------Main functions----------------------------------

def printdoc():
    printhello()
    print ""
    print "Usage : tcpsteg <client|server> <bindhost> <bindport> <remotehost> <remoteport> <password>";
    print "[-c <command>]"
    print "[-p <password>]"
    print "[-v]"
    print "Start the tcpsteg client or server";
    print ""
    print "bindhost : name of the interface on which tcpsteg will be bound,"
    print "bindport : tcp port on which tcpsteg will be bound"
    print "remotehost : ip address or name of the remote host to forward tcp traffic"
    print "remoteport : tcp port of remote host to forward tcp traffic"
    print "password : string to authenticate client to the server."
    print "           WARNING : this string is sent in plaintext."
    print ""
    print "-c <command> : attach a process to the client or the server."
    print "               Typical use : '-c /bin/sh' or '-c cmd.exe'"
    print "               WARNING : the child process will have the same rights than tcpsteg !"
    print "-v : verbose mode (on stderr)"
    print ""
    print "Examples of use :"
    print "tcpteg client 127.0.0.1 7777 172.16.1.1 hello 8888"
    print "tcpteg server 172.16.1.1 8888 127.0.0.1 hello 80 -c /bin/sh"

def printhello():
    print "TCP Steg[anographier]"
    print "By Michael Coquard and Yves Stadler"
    

if __name__=='__main__':
    # nombre d'arguments incluant le nom du script
    num_of_std_args = 7

    if len(sys.argv) < num_of_std_args:
        printdoc()
        sys.exit(1)

    # chargement des arguments facultatifs de la ligne de commande
    # switchs et arguments attendus
    sw = [("-c",1),("-v",0)]
    args = {}
    i = 0
    l = []
    for s in sys.argv[num_of_std_args:]:
        # on regarde si des arguments n'ont pas été traités
        if(i != 0):
            l.append(s)
            i -= 1
        else:
            l = []
            # on détecte un switch dans la ligne de commande
            for a in sw:
                if(s == a[0]):
                    i = a[1]
                    # ajout du switch au dico
                    args[s] = l
                    break
            else:
                # switch non trouvé
                printdoc()
                sys.exit(1)

    # si i n'est pas à zero, tous les arguments n'ont pas été traités !
    if(i != 0):
        printdoc()
        sys.exit(1)

    # traitement des arguments standards
    type = sys.argv[1];
    if type == "server":
        isserver = True
    elif type == "client":
        isserver = False
    else:
        printdoc()
        sys.exit(1)
    bindhost = sys.argv[2];
    try:
        bindport = int(sys.argv[3])
    except:
        print >> sys.stderr, "Bad bind port format !"
        sys.exit(1)
    remotehost = sys.argv[4];
    try:
        remoteport = int(sys.argv[5])
    except:
        print >> sys.stderr, "Bad remote port format !"
        sys.exit(1)
    password = sys.argv[6]
    # traitement des arguments facultatifs
    if args.has_key("-v"):
        verb = True
    else:
        verb = False
        
    if args.has_key("-c"):
        command = args["-c"][0]
    else:
        command = None

    # démarrage
    if isserver:
        # server
        server(bindhost,bindport,remotehost,remoteport,verb,command,password)
    else:
        # client
        client(bindhost,bindport,remotehost,remoteport,verb,command,password)
        