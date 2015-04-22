#!/usr/bin/env python
# coding=utf-8
#
from re import search, sub, match
from os.path import join
from s2ge import *
import s2gd
#
###########################
# LAMBDA FUNCTIONS ########
###########################
# match a certain expression at start of string
match_start  = lambda expr,line: match(r'\s*(%s)[^a-zA-Z0-9]'%expr,line)
# ----------
# RECONSIDER
# ----------
# strip unwanted delimiters from string
strip_d      = lambda s,d: sub(d,'',s)
# get first argument (cf getfargs)
getarg1      = lambda l: strip_d(get_fargs(l)[0],'\'')
# get next arg
getnextarg   = lambda lst: lst.pop(0).lower().strip('\'')
getnextargNL = lambda lst: lst.pop(0).strip('\'')
#
###########################
# FUNCTIONS ###############
###########################
#
# +++++++++++++++++++++++++++++++++++++++++
# GET FARGS :
#	get arguments of function str
#
#	<in>:	string like plot(x,y,'linewidth',2.0)
# 	<out>:	list of arguments ['x','y','linewidth','2.0']
def get_fargs(line):
	# get core
 	stack = search(
 				r'^\s*(?:\w+)\(\s*'					 # match "marker("
 				r'(.*?)'							 # all arguments
 				r'(?:\)\s*;?\s*)'					 # end bracket
				r'((?:%s).*)?$'%s2gd.csd['comment'], # and rest of line (possible comm)
				line).group(1)
 	#
 	# browse the chars in arglst, separate with commas
 	# but not when within expression such as 
 	# '..,..' or "..,.." or [..,..] etc.
 	#
 	arglst = []
	while stack:
		stack  = stack.strip()
		curidx = 0
		maxidx = len(stack)
		curarg = ''
		key    = stack[0]
		isopen = key in s2gd.keyopen 		# ', ", [, (, {
		while curidx<maxidx-1 and isopen:
			curchar = stack[curidx]
			curarg += curchar
			curidx += 1
			nxtchar = stack[curidx]
			isopen  = not(nxtchar==s2gd.keyclose[key])
		while curidx<maxidx and not(stack[curidx]==','):
			curarg += stack[curidx]
			curidx += 1
		stack = stack[curidx+1:]
		arglst.append(curarg)
		curarg = ''
	#
 	return arglst
#
# +++++++++++++++++++++++++++++++++++++++++++
# ARRAY X
# 	extract numbers in array string '[a b c]'
#
#	<in>: 	string like '[2.0 -2,3]'
#	<out>:	numbers ['2.0','-2','3']
#	<rmk>:	does not interpret expressions
def array_x(s):
	array = []
	# strip ends (-[-stuff-]- extract stuff)
	core = match(r'(\s*\[?)([^\[^\]]+)(\]?\s*)',s).group(2)
	# replace ',' by space
	left = sub(',',' ',core)
	# ATTEMPT - if sequence
	nc = left.count(':')
	if nc==1: # 1:5
		spl        = match(r'(^[^:]+):([^:]+$)',left);
		first,last = float(spl.group(1)), float(spl.group(2))
		seq,cur    = [str(first)], first
		while cur<=last-1:
			cur+=1
			seq.append(str(cur))
		array = seq
	elif nc==2:
		spl             = match(r'(^[^:]+):([^:]+):([^:]+$)',left)
		first,step,last = float(spl.group(1)), float(spl.group(2)), float(spl.group(3))
		seq,cur         = [str(first)],first
		while cur<=last-step:
			cur+=step
			seq.append(str(cur))
		array = seq
	else:
		array = left.split(' ')
	return [sub(' ','',e) for e in array]
#
# +++++++++++++++++++++++++++++++++++++++++++
# GET COLOR:
# 	(internal) read a 'color' option and
#	return something in GLE format
def get_color(optstack):
	opt   = getnextarg(optstack)
	color = ''
	a     = 0
	# option given form [r,g,b,a?]
	rgbsearch  = search(r'\[\s*([0-9]+\.?[0-9]*|\.[0-9]*)\s*[,\s]\s*([0-9]+\.?[0-9]*|\.[0-9]*)\s*[,\s]\s*([0-9]+\.?[0-9]*|\.[0-9]*)(.*)',opt)
	if rgbsearch:
		r,g,b  		= rgbsearch.group(1,2,3)
		alphasearch = search(r'([0-9]+\.?[0-9]*|\.[0-9]*)',rgbsearch.group(4))
		a = '1' if not alphasearch else alphasearch.group(1)
		color = 'rgba(%s,%s,%s,%s)'%(r,g,b,a)
	# option is x11 name + 'alpha'
	elif optstack and optstack[0].lower().strip('\'')=='alpha':
		optstack.pop(0)
		opta  = getnextarg(optstack)
		# col -> rgba (using svg2rgb dictionary see s2gd.srd)
		r,g,b = s2gd.srd.get(opt,(128,128,128))
		a     = round(float(opta)*100)
		color = 'rgba255(%i,%i,%i,%2.1f)'%(r,g,b,a)
	else: # just colname
		color = opt
		# if in matlab format (otherwise x11 name)
		if color in ['r','g','b','c','m','y','k','w']:
			color = s2gd.md[color]
	trsp = False if a==0 or a=='1' else True
	return color,trsp,optstack
#
# +++++++++++++++++++++++++++++++++++++++++++
def close_ellipsis(l,script_stack):
	# gather lines in case continuation (...)
	regex   = r'(.*?)(?:\.\.\.\s*(?:%s.*)?$)'%s2gd.csd['comment']
	srch_cl = search(regex,l)
	if srch_cl:
		line_open = True
		nloops = 0
		l = srch_cl.group(1)
		while line_open and nloops<100:
			nloops += 1
			lt      = script_stack.pop(0)
			srch_cl = search(regex,lt)
			if srch_cl:
				l  += srch_cl.group(1)
			else:
				line_open = False
				l+=lt
		if line_open:
			raise S2GSyntaxError(l,'<::line not closed::>')
	return l, script_stack
#
# +++++++++++++++++++++++++++++++++++++++++++
# READ PLOT:
#	read a 'plot(...)' line, extracts script
#	code to output data, generates GLE bloc
#	to input in GLE figure
#
#	<in>:	line (from core part of script doc)
#	<out>:	returns line + output line
def read_plot(line, figc, plotc):
	plt,tls  = {},{}
	# default options
	plt['lwidth'] = ' lwidth 0 '
	plt['msize']  = ' msize 0.2 '
	tls['line']   = ''
	tls['marker'] = ''
	tls['color']  = ' darkblue '
	# flags of options done
	flags = {'lstyle':False,'lwidth':False,'msize':False,'mface':False}
	# get plot arguments
	args = get_fargs(line)
	# ------------------------------------------
	# SCRIPT -----------------------------------
	# generate script to output appropriate data
	sta = 2; # index of args where options start
	# case one var: plot(x), plot(x,'+r'), ...
	if len(args)==1 or match(r'^\s*\'',args[1]):
		script = 'x__ = %s%s\n'%(s2gd.csd['span']%s2gd.csd['numel']%args[0],s2gd.csd['EOL'])
		script+= 'y__ = %s%s\n'%(args[0],s2gd.csd['EOL'])
		sta    = 1
	# case two vars plot(x,y,'+r')
	else:
		script = 'x__ = %s%s\n'%(args[0],s2gd.csd['EOL'])
		script+= 'y__ = %s%s\n'%(args[1],s2gd.csd['EOL'])
	#
	vecx   = s2gd.csd['vec']%'x__'
	vecy   = s2gd.csd['vec']%'y__'
	script+= 'c__ = %s%s\n'%(s2gd.csd['cbind']%(vecx,vecy),s2gd.csd['EOL'])
	dfn    = "%sdatplot%i_%i.dat"%(s2gd.tind,figc,plotc)
	script+= "%s%s\n"%(s2gd.csd['writevar'].format(dfn,'c__'),s2gd.csd['EOL'])
	#
	plt['script'] = script
	# ---------------------------------
	# GLE -----------------------------
	# generate gle code to read options
	if len(args)>sta:
		optsraw = args[sta:]
		while optsraw:
			opt = getnextarg(optsraw)
			#
			# LSTYLE
			#
			# patterns of the form '-+r'
			p_lstyle = r'^(?![ml0-9])([-:]?)([-\.]?)([\+o\*\.xs\^]?)([rgbcmykw]?)'
			lstyle = match(p_lstyle,opt)
			if lstyle and not flags['lstyle']:
				flags['lstyle']=True
				#
				# line (continuous, dashed, ...)
				l_1 = lstyle.group(1)
				l_2 = lstyle.group(2)
				if   match(r':', l_1): 	tls['line'] = '2' 	# dotted
				elif match(r'-', l_1) and \
					 match(r'\.',l_2): 	tls['line'] = '6'	# dashed-dotted
				elif match(r'-', l_1) and \
					 match(r'-', l_2): 	tls['line'] = '3'	# dashed
				elif match(r'-', l_1):	tls['line'] = '0'	# standard
				#
				# marker
				l_3 = lstyle.group(3)
				if   match(r'\+',l_3): 	tls['marker'] = 'plus'
				elif match(r'o', l_3):	tls['marker'] = 'circle'
				elif match(r'\*',l_3): 	tls['marker'] = 'star'
				elif match(r'x', l_3):	tls['marker'] = 'cross'
				elif match(r's', l_3):	tls['marker'] = 'square'
				elif match(r'\^',l_3):	tls['marker'] = 'triangle'
				#
				# color
				l_4 = lstyle.group(4)
				tls['color'] = s2gd.md.get(l_4,'blue')
			#
			# COLOR OPTION (accept x11 names)
			#
			elif opt=='color':
				tls['color'] = getnextarg(optsraw)
				if tls['color'] in ['r','g','b','c','m','y','k','w']:
					tls['color'] = s2gd.md[tls['color']]
			#
			# LWIDTH OPTION
			#
			elif opt=='linewidth' and not flags['lwidth']:
				flags['lwidth']=True
				opt = getnextarg(optsraw)
				lw  = float(opt)
				lw  = round(((lw/3)**.7)/10,2) # magic...
				plt['lwidth'] = ' lwidth '+str(lw)+' '
			#
			# MSIZE OPTION
			#
			elif opt=='markersize' and not flags['msize']:
				flags['msize']=True
				opt = getnextarg(optsraw)
				ms  = float(opt)
				ms  = round(((ms/5)**.5)/5,2)
				plt['msize'] = ' msize '+str(ms)+' '
			#
			# MFACE OPTION
			#
			elif opt=='markerfacecolor' and not flags['mface']:
				flags['mface']=True
				optsraw.pop(0) # actually we don't care what color is given (yet)
	#
	# if just marker no line, if no marker no line -> lstyle 0
	lb,mb  = bool(tls['line']),bool(tls['marker'])
	lbool  = lb or not mb
	lsty   = tls['line']+'0'*(not lb)
	line   = ('lstyle '+lsty)*lbool
	fill   = 'f'*(tls['marker'] in ['circle','square','triangle'])*flags['mface']
	marker = 'marker '*mb+fill+tls['marker']
	color  = 'color '+tls['color']
	plt['lstyle'] = ' '+line+' '+marker+' '+color+' '
	return plt
#
# +++++++++++++++++++++++++++++++++++++++++++
# READ BAR:
#	read a 'bar(...)' line, extracts script
#	code to output data, generates GLE bloc
#	to input in GLE figure
#
#	<in>:	line (from core part of script doc)
#	<out>:	returns line + output line
def read_bar(line,figc,plotc):
	bar = {}
	# default options
 	bar['edgecolor'] = 'white'
 	bar['facecolor'] = 'cornflowerblue'
 	bar['alpha'] 	 = False
 	bar['width']	 = 1
 	bar['xdticks']   = '1'
 	bar['flticks'] 	 = False
 	# get plot arguments
 	args = get_fargs(line)
 	# ------------------------------------------
 	# SCRIPT -----------------------------------
 	# generate script to output appropriate data
 	# > syntax:
 	# 	command: bar(x,...)
 	#	 			...,'Normalization','count|countdensity|probability|pdf|cumcount|cdf'
 	#				...,'Facecolor',svgcol|matlabcol|rgb|rgba,'Alpha'?,0.8
 	#				...,'Edgecolor',svgcol|matlabcol|rgb
 	#
 	xname  = strip_d(args.pop(0),'\'')
 	yname  = ''
 	if args and not (search(r'^\s*\'',args[0]) or args[0].isdigit()):
 		yname = strip_d(args.pop(0),'\'')
 	a='1' # alpha
 	b='1' # alpha for edge (a bit weird but up to the user to decided)
 	if args:
	 	optsraw = args
	 	while optsraw:
	 		opt = getnextarg(optsraw)
	 		if opt.isdigit() or opt=='width':
	 			if opt=='width':
	 				opt = getnextarg(optsraw)
	 			bar['width'] = float(opt)
	 		elif opt=='xdticks':
	 			opt = getnextarg(optsraw)
	 			bar['xdticks'] = opt
	 		elif opt=='flticks':
	 			bar['flticks'] = True
	 		elif opt in ['r','g','b','c','m','y','k','w']:
				bar['facecolor']=s2gd.md[opt]
			elif opt in ['color','facecolor']:
				bar['facecolor'],a,optsraw = get_color(optsraw)
	 		elif opt=='edgecolor':
	 			bar['edgecolor'],b,optsraw = get_color(optsraw)
	#
 	if not (a=='1' or b=='1'): bar['alpha']=True
 	#
	script = 'x__  = %s%s\n'%(xname ,s2gd.csd['EOL'])
	if yname:
		vecx    = s2gd.csd['vec']%'x__'
		script += 'y__ = %s%s\n'%(s2gd.csd['asmatrix']%yname,s2gd.csd['EOL'])
		script += 'y__ = %s%s\n'%(s2gd.csd['tifrow'].format('y__'),s2gd.csd['EOL'])
		script += 'c__ = %s%s\n'%(s2gd.csd['cbind']%(vecx,'y__'),s2gd.csd['EOL'])
	else:
	 	script += 'y__ = %s%s\n'%(s2gd.csd['asmatrix']%'x__',s2gd.csd['EOL'])
	 	script += 'y__ = %s%s\n'%(s2gd.csd['tifrow'].format('y__'),s2gd.csd['EOL'])
	 	script += 'lsp = %s%s\n'%(s2gd.csd['span']%s2gd.csd['nrows']%'y__',s2gd.csd['EOL'])
	 	script += 'c__ = %s%s\n'%(s2gd.csd['cbind']%(s2gd.csd['vec']%'lsp','y__'),s2gd.csd['EOL'])
	#
 	script += 'ncols__ = %s%s\n'%(s2gd.csd['ncols']%'y__',s2gd.csd['EOL'])
	#
	dfn    = "%sdatbar%i_%i.dat"%(s2gd.tind,figc,plotc)
  	script+= '%s%s\n'%(s2gd.csd['writevar'].format(dfn,'c__'),s2gd.csd['EOL'])
  	script+= 'c2__ = %s%s\n'%('ncols__',s2gd.csd['EOL']) 
  	dfn2   = "%sdatbar%i_%i_side.dat"%(s2gd.tind,figc,plotc)
  	script+= '%s%s\n'%(s2gd.csd['writevar'].format(dfn2,'c2__'),s2gd.csd['EOL'])
 	bar['script'] = script
 	return bar
