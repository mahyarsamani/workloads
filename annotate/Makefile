
CC=gcc

all: papi gem5se gem5fs native

papi: make_dir libroi.papi.a libroi.papi.so roi.papi
gem5se: make_dir libroi.gem5se.a libroi.gem5se.so roi.gem5se
gem5fs:make_dir libroi.gem5fs.a libroi.gem5fs.so roi.gem5fs
native: make_dir libroi.native.a libroi.native.so roi.native

make_dir:
	mkdir -p lib

libroi.papi.a: roi.c
	$(CC) -c $< -o lib/$@ -DPAPI --static -Ipapi/install/include

libroi.gem5se.a: roi.c
	$(CC) -c $< -o lib/$@ -DGEM5SE --static -Igem5/include

libroi.gem5fs.a: roi.c
	$(CC) -c $< -o lib/$@ -DGEM5FS --static -Igem5/include

libroi.native.a: roi.c
	$(CC) -c $< -o lib/$@ --static

libroi.papi.so: roi.c
	$(CC) -c $< -o lib/$@ -DPAPI -Ipapi/install/include

libroi.gem5se.so: roi.c
	$(CC) -c $< -o lib/$@ -DGEM5SE -Igem5/include

libroi.gem5fs.so: roi.c
	$(CC) -c $< -o lib/$@ -DGEM5FS -Igem5/include

libroi.native.so: roi.c
	$(CC) -c $< -o lib/$@

roi.papi: roi.c
	$(CC) -c $< -o lib/$@ -DPAPI -Ipapi/install/include

roi.gem5se: roi.c
	$(CC) -c $< -o lib/$@ -DGEM5SE -Igem5/include

roi.gem5fs: roi.c
	$(CC) -c $< -o lib/$@ -DGEM5FS -Igem5/include

roi.native: roi.c
	$(CC) -c $< -o lib/$@

clean:
	rm -f lib/libroi.papi.a lib/libroi.papi.so lib/roi.papi
	rm -f lib/libroi.gem5se.a lib/libroi.gem5se.so lib/roi.gem5se
	rm -f lib/libroi.gem5fs.a lib/libroi.gem5fs.so lib/roi.gem5fs
	rm -f lib/libroi.native.a lib/libroi.native.so lib/roi.native
