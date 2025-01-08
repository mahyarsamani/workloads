
CC=gcc

all: papi gem5se gem5fs native

papi: make_dir libannotate.papi.a libannotate.papi.so annotate.papi
gem5se: make_dir libannotate.gem5se.a libannotate.gem5se.so annotate.gem5se
gem5fs:make_dir libannotate.gem5fs.a libannotate.gem5fs.so annotate.gem5fs
native: make_dir libannotate.native.a libannotate.native.so annotate.native

make_dir:
	mkdir -p lib

libannotate.papi.a: annotate.c
	$(CC) -c $< -o lib/$@ -DPAPI --static -Ipapi/install/include

libannotate.gem5se.a: annotate.c
	$(CC) -c $< -o lib/$@ -DGEM5SE --static -Igem5/include

libannotate.gem5fs.a: annotate.c
	$(CC) -c $< -o lib/$@ -DGEM5FS --static -Igem5/include

libannotate.native.a: annotate.c
	$(CC) -c $< -o lib/$@ --static

libannotate.papi.so: annotate.c
	$(CC) -c $< -o lib/$@ -DPAPI -Ipapi/install/include

libannotate.gem5se.so: annotate.c
	$(CC) -c $< -o lib/$@ -DGEM5SE -Igem5/include

libannotate.gem5fs.so: annotate.c
	$(CC) -c $< -o lib/$@ -DGEM5FS -Igem5/include

libannotate.native.so: annotate.c
	$(CC) -c $< -o lib/$@

annotate.papi: annotate.c
	$(CC) -c $< -o lib/$@ -DPAPI -Ipapi/install/include

annotate.gem5se: annotate.c
	$(CC) -c $< -o lib/$@ -DGEM5SE -Igem5/include

annotate.gem5fs: annotate.c
	$(CC) -c $< -o lib/$@ -DGEM5FS -Igem5/include

annotate.native: annotate.c
	$(CC) -c $< -o lib/$@

clean:
	rm -f lib/libannotate.papi.a lib/libannotate.papi.so lib/annotate.papi
	rm -f lib/libannotate.gem5se.a lib/libannotate.gem5se.so lib/annotate.gem5se
	rm -f lib/libannotate.gem5fs.a lib/libannotate.gem5fs.so lib/annotate.gem5fs
	rm -f lib/libannotate.native.a lib/libannotate.native.so lib/annotate.native
