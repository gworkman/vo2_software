import serial
import asyncio
import sys
import struct
import time


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
        if data_packet[0] == 0:
            running = data_packet[1] == 1
        elif data_packet[0] == 1:
            cycle_count = int.from_bytes(data_packet[1:], byteorder='little')
        elif data_packet[0] == 2:
            source_voltage = struct.unpack('<f', data_packet[1:])[0]
        elif data_packet[0] == 3:
            current1 = struct.unpack('<f', data_packet[1:])[0]
        elif data_packet[0] == 4:
            current2 = struct.unpack('<f', data_packet[1:])[0]
        elif data_packet[0] == 5:
            button = data_packet[1] > 0
        elif data_packet[0] == 6:
            micros_on = int.from_bytes(data_packet[1:], byteorder='little')
        elif data_packet[0] == 7:
            micros_off = int.from_bytes(data_packet[1:], byteorder='little')
        elif data_packet[0] == 9:
            # sample_count = int.from_bytes(data_packet[1:], byteorder='little')
            # adc_data_raw = ser.read(sample_count * 2)
            # adc_data = struct.unpack(f'<{sample_count}H', adc_data_raw)
            # print(adc_data)
            print('got packet 9')
        elif record_file is not None and not record_file.closed:
            try:
                print(f'{time.time()}, {running:d}, {cycle_count:d}, {source_voltage:f}, {current1:f}, {current2:f}, {button:d}, {micros_on:d}, {micros_off:d}', file=record_file)
            except:
                print('[error] failed to write to csv file')

        await asyncio.sleep(0)


async def stop_record(after_seconds):
    global record_file
    await asyncio.sleep(after_seconds)
    if record_file:
        close_file(record_file)
        record_file = None


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
            packet = bytes([0, 1, 0, 0, 0])
        elif command[0].lower() == 'stop':
            packet = bytes([0, 0, 0, 0, 0])
            if record_file:
                await stop_record(after_seconds=0)
        elif command[0].lower() == 'cycle':
            try:
                cycle_stop = int(command[1])
                packet = struct.pack('<BI', 1, cycle_stop)
            except:
                print('[error] failed to parse an integer from command arguments')
                print('command format: cycle <number of cycles>')

        elif command[0].lower() == 'list':
            print_status()
        elif command[0].lower() == 'on':
            try:
                on_time = int(command[1])
                packet = struct.pack('<BI', 6, on_time)
            except:
                print('[error] failed to parse an integer from command arguments')
                print('command format: on <microseconds>')
        elif command[0].lower() == 'off':
            try:
                off_time = int(command[1])
                packet = struct.pack('<BI', 7, off_time)
            except:
                print('[error] failed to parse an integer from command arguments')
                print('command format: off <microseconds>')
        elif command[0].lower() == 'record':
            try:
                record_file = open(command[1], 'w')
                print(
                    'timestamp,running,cycle_count,source_voltage,current1,current2,button,micros_on,micros_off', file=record_file)
                asyncio.create_task(stop_record(after_seconds=30))
            except:
                print('[error] failed to open the file for writing')
                print('command format: record <file path>')
        elif command[0].lower() == 'program':
            packet = bytes([9, 1, 0, 0, 0])
            print(packet)
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


ser = serial.Serial(sys.argv[1], 115200, timeout=2)

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
