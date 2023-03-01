#!/usr/bin/python3
# MIT License
#
# Copyright (c) 2023 zsdotkr@gmail.com
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Requres python 3.2+

# github : https://github.com/zsdotkr/pico-map
# I got a hint for this code from adafruit github (https://github.com/adafruit/linker-map-summary)

# To see the sector size briefly : 'size --format=GNU emm_rp.elf'
# * text : .text + .data + .boot2
# * data : .rodata + .binary_info
# * bss : .bss


import sys
import os
import argparse

class SrcFile():
	def __init__(self):
		self.code = 0	# code in ROM
		self.rodata = 0 # data in ROM (read only)
		self.data = 0	# initialized data in RAM
		self.bss = 0	# uninitialized data in RAM
		self.etc = 0

	def total(self):
		return self.code + self.rodata + self.data + self.bss + self.etc

	def add(self, section, size):
		if section.startswith('.text'):
			self.code += size
		elif section.startswith('.rodata'):
			self.rodata += size
		elif section.startswith('.data'):
			self.data += size
		elif section.startswith('.bss'):
			self.bss += size
		elif section.startswith(('.comment', '.debug', '.ARM.attributes')):
			return # ignore
		else:
			self.etc += size


class Section():
	def __init__(self):
		self.size = 0
		self.start = 0
	def add(self, start, size):
		self.size += size
		self.start = start
	def total():
		return self.size


class Memory():
	def __init__(self, name, start, length):
		self.name = name
		self.start = start
		self.end = start + length - 1
		self.total = length
		self.use = 0
		self.section = {} # Section

	def add(self, section_name, start, size):
		if section_name not in self.section:
			self.section[section_name] = Section()
		self.section[section_name].add(start, size)
		self.use += size

# ---------- Global ----------

mem_list = []
file_list = {}

# ---------- functions ----------

def find_mem(name):
	for mem in mem_list:
		if mem.name == name:
			return mem

def add_section_to_mem(section, start, size):
	for mem in mem_list:
		if (start >= mem.start) and ((start + size-1) <= mem.end):
			mem.add(section, start, size)
			return

def kb(size):
	if size % 1024 == 0:
		return f'{int(size/1024):6}KB'
	else:
		return f'{(size/1024):6.1f}KB'

# ---------- Main ----------

def main():
	parser = argparse.ArgumentParser(description='Summarises overall object size for RP2040 from "elf.map" file')
	parser.add_argument('map_file', help="A map file ('elf.map') generated by passing -M/--print-map to ld during linking.")
	parser.add_argument('--total', action='store_true', help="Sort by total size (default)")
	parser.add_argument('--code', action='store_true', help="Sort by CODE section (in FLASH or RAM)")
	parser.add_argument('--bss', action='store_true', help="Sort by '.bss' section (Uninitialized data area in RAM)")
	parser.add_argument('--data', action='store_true', help="Sort by '.data' section (Initialized data area in RAM)")
	parser.add_argument('--rodata', action='store_true', help="Sort by '.rodata' section size (Initialized data area in FLASH)")

	args = parser.parse_args()

	with open(args.map_file) as f:
		lines = iter(f)

		### advance to "Memory Configuration"
		for line in lines:
			if line.strip() == "Memory Configuration":
				break

		for line in lines:
			line = line.strip('\n')

			if line.strip() == "Linker script and memory map":
				break

			### parse "Memory Configuration"
			part = line.split(None, 4)
			if len(part) < 3:
				continue

			try:
				mem = Memory(part[0], int (part[1], 16), int (part[2], 16))
			except:
				continue

			if not part[0].startswith('*'):	# exclude '*default*'
				mem_list.append(mem)

		### parse "Linker script and memory map"

		cur_sec = None
		split_line = None

		for line in lines:
			line = line.strip('\n')

			### check section size
			if line.startswith("."):
				part = line.split(None, 3)

				if len(part) >= 3:
					start = int(part[1], 16)
					size = int(part[2], 16)
					if (size > 0):
						add_section_to_mem(part[0], start, size)

			if split_line: # Glue a line that was split in two back together
				if line.startswith(' ' * 16):
					line = split_line + line
				else:  # Shouldn't happen
					print("Warning: discarding line ", split_line)
				split_line = None

			if line.startswith((".", " .", " *fill*")):
				part = line.split(None, 3)

				if (line.startswith('.')): # start of section
					cur_sec = part[0]

				elif len(part) == 1 and len(line) > 14:
					split_line = line

				elif len(part) >= 3 and "=" not in part and 'before' not in part:
					if part[0] == '*fill*': # CAUTION : sometimes linker generate incorrect value for 'fill' section
						source = part[0]
						size = int(part[-1], 16)

					else:
						source = part[-1]
						size = int(part[-2], 16)
						start = int(part[-3], 16)

					# combine several '*.a' files in one file
					# if '.a(' in source:
					# 	source = source[:source.index('.a(') + 2]
					# elif source.endswith('.o'):
					# 	where = max(source.rfind('\\'), source.rfind('/'))
					# 	if where:
					# 		source = source[:where + 1] + '*.o'

					if source not in file_list:
						file_list[source] = SrcFile()

					file_list[source].add(cur_sec, size)

		### Append '.data' section to FLASH area, elf.map don't provide this info.

		try:
			ram_data = find_mem('RAM').section['.data']
			rom = find_mem('FLASH')
			add_section_to_mem('.data(image)', rom.start + rom.use, ram_data.size)
		except:
			pass

		### Sorting option

		sources = list(file_list.keys())
		if args.code:
			sources.sort(key = lambda x: file_list[x].code)
		elif args.bss:
			sources.sort(key = lambda x: file_list[x].bss)
		elif args.rodata:
			sources.sort(key = lambda x: file_list[x].rodata)
		elif args.data:
			sources.sort(key = lambda x: file_list[x].data)

		### Print out

		print('********** File **********')
		sumtotal = sumcode = sumdata = sumbss = sumrodata = sumetc = 0
		print(' Total   code rodata   data    bss    etc FILE')
		for source in sources:
			ent = file_list[source]
			sumcode += ent.code
			sumdata += ent.data
			sumbss += ent.bss
			sumrodata+= ent.rodata
			sumetc+= ent.etc
			sumtotal += ent.total()

			print('%6d %6d %6d %6d %6d %6d %s'%(ent.total(), ent.code, ent.rodata,
				ent.data, ent.bss, ent.etc, source))

		print('%6d %6d %6d %6d %6d %6d SUMMARY'%(sumtotal, sumcode, sumrodata, sumdata, sumbss, sumetc))
		print(' Total   code rodata   data    bss    etc FILE')
		print("*) In some cases, the values may not match exactly (I've seen the linker miscalculate the '*fill*' size)")

		print(' ')
		print('********** Memory **********')
		for mem in mem_list:
			print("%10s  %08xh ~ %08xh  Total %8s  Used %6dB  Ratio %5.1f%%"%
				(mem.name, mem.start, mem.end, kb(mem.total), mem.use, (mem.use * 100) / (mem.end - mem.start)))

		print(' ')
		print('********** Sector **********')
		for mem in mem_list:
			for sect_name in mem.section:
				sect = mem.section[sect_name]
				print("%10s : %15s %08xh ~ %08xh Size %8s (%6dB)  %6.2f%%"%
					(mem.name,
					sect_name, sect.start, sect.start + sect.size - 1, kb(sect.size), sect.size,
					(sect.size * 100) / mem.use	))

		print(" ")

if __name__ == '__main__':
	main()

