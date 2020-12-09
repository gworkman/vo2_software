#!/usr/bin/env python

import serial
import asyncio
import sys
import struct
import time

RUN = 0
CYCLE = 1
VOLTAGE = 2
CURRENT1 = 3
CURRENT2 = 4
BUTTON = 5
MICROS_ON = 6
MICROS_OFF = 7
PROGRAM = 8
DEBUG = 9
RAW_ADC = 10


class Prompt:
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.q = asyncio.Queue()
        self.loop.add_reader(sys.stdin, self.got_input)

    def got_input(self):
        asyncio.ensure_future(self.q.put(sys.stdin.readline()), loop=self.loop)

    async def __call__(self, msg, end='\n', flush=False):
        print(msg, end=end, flush=flush)
        return (await self.q.get()).rstrip('\n')


async def update_loop():
    global source_voltage, current1, current2, micros_on, micros_off, button, running, cycle_count, record_file

    while True:
        data_packet = ser.read(5)
        if data_packet[0] == RUN:
            running = data_packet[1] == 1
        elif data_packet[0] == CYCLE:
            cycle_count = int.from_bytes(data_packet[1:], byteorder='little')
        elif data_packet[0] == VOLTAGE:
            source_voltage = struct.unpack('<f', data_packet[1:])[0]
        elif data_packet[0] == CURRENT1:
            current1 = struct.unpack('<f', data_packet[1:])[0]
        elif data_packet[0] == CURRENT2:
            current2 = struct.unpack('<f', data_packet[1:])[0]
        elif data_packet[0] == BUTTON:
            button = data_packet[1] > 0
        elif data_packet[0] == MICROS_ON:
            micros_on = int.from_bytes(data_packet[1:], byteorder='little')
        elif data_packet[0] == MICROS_OFF:
            micros_off = int.from_bytes(data_packet[1:], byteorder='little')
        elif data_packet[0] == PROGRAM:
            pass
        elif data_packet[0] == RAW_ADC:
            adc_data_len = int.from_bytes(data_packet[1:], byteorder='little')
            raw_adc_data = ser.read(adc_data_len)
            adc_data = struct.unpack(f'<{int(adc_data_len/2)}H', raw_adc_data)
            if record_file is not None and not record_file.closed:
                try:
                    print('\n'.join([str(val)
                                     for val in adc_data]), file=record_file)
                except:
                    print('[error] failed to write to csv file')

        await asyncio.sleep(0)


async def stop_record(after_seconds):
    global record_file
    await asyncio.sleep(after_seconds)
    if record_file:
        close_file(record_file)
        record_file = None
        print('recording finished')


def close_file(use_file):
    try:
        use_file.flush()
        use_file.close()
    except:
        print('[error] failed to properly close file')


def print_status():
    global source_voltage, current1, current2, micros_on, micros_off, button, running, cycle_count, run_until_cycle, record_file
    print()
    print(f'running: {running}')
    print(f'cycle_count: {cycle_count}')
    print(f'source_voltage: {source_voltage:0.3f}V')
    print(f'current1: {current1:0.3f}A')
    print(f'current2: {current2:0.3f}A')
    print(f'button: {button}')
    print(f'micros_on: {micros_on}')
    print(f'micros_off: {micros_off}')
    print(f'recording: {record_file is not None}')
    print()


async def main():
    global record_file
    prompt = Prompt()
    asyncio.create_task(update_loop())
    while True:
        command = await prompt('-> ', end='', flush=True)
        command = command.split(' ')
        packet = None

        if command[0].lower() == 'run':
            packet = bytes([RUN, 1, 0, 0, 0])
        elif command[0].lower() == 'stop':
            packet = bytes([RUN, 0, 0, 0, 0])
            if record_file:
                await stop_record(after_seconds=0)
        elif command[0].lower() == 'cycle':
            try:
                cycle_stop = int(command[1])
                packet = struct.pack('<BI', CYCLE, cycle_stop)
            except:
                print('[error] failed to parse an integer from command arguments')
                print('command format: cycle <number of cycles>')

        elif command[0].lower() == 'list':
            print_status()
        elif command[0].lower() == 'on':
            try:
                on_time = int(command[1])
                packet = struct.pack('<BI', MICROS_ON, on_time)
            except:
                print('[error] failed to parse an integer from command arguments')
                print('command format: on <microseconds>')
        elif command[0].lower() == 'off':
            try:
                off_time = int(command[1])
                packet = struct.pack('<BI', MICROS_OFF, off_time)
            except:
                print('[error] failed to parse an integer from command arguments')
                print('command format: off <microseconds>')
        elif command[0].lower() == 'record':
            try:
                record_file = open(command[1], 'w')
                print('raw_adc', file=record_file)
                asyncio.create_task(stop_record(after_seconds=10))
            except:
                print('[error] failed to open the file for writing')
                print('command format: record <file path>')
        elif command[0].lower() == 'program':
            packet = bytes([PROGRAM, 0, 0, 0, 0])
        elif command[0].lower() == 'debug':
            packet = bytes([DEBUG, 0, 0, 0, 0])
        elif command[0].lower() == 'quit' or command[0].lower() == 'q':
            if record_file:
                await stop_record(after_seconds=0)
            ser.close()
            exit()

        elif command[0] != '':
            print('''
Invalid command format. Valid commands are:
run                 - starts running a study
stop                - stops running the study and stops recording data
cycle <uint32_t>    - set the stop condition (cycle number). Max value is 4,294,967,295
list                - display current status
on <uint32_t>       - set PWM on time (microseconds)
off <uint32_t>      - set PWM off time (microseconds)
record <string>     - streams 30 seconds of received data to the given file in csv format
quit                - quits this program
help                - show this help menu''')

        if packet is not None:
            if len(packet) == 5:
                ser.write(packet)
            else:
                print(f'[error] command packet length is {len(packet)} bytes')


ser = None
try:
    ser = serial.Serial(sys.argv[1], 115200)
except:
    print('Error opening serial port')
    print('Usage: vo2_client.py /path/to/port')
    exit()

source_voltage = 0.0
current1 = 0.0
current2 = 0.0
micros_on = 0
micros_off = 0
button = False
running = False
cycle_count = 0
run_until_cycle = -1
record_file = None

asyncio.run(main())
