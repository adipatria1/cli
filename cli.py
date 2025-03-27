import os
import random
import sys
import psutil
import logging
import gc
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, vfx, ImageClip, CompositeVideoClip
from moviepy.video.fx.freeze import freeze
from moviepy.video.fx.resize import resize
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('recap_generator.log')
    ]
)

def force_garbage_collection():
    """Force garbage collection to free memory"""
    gc.collect()
    if hasattr(gc, 'garbage'):
        del gc.garbage[:]

def check_system_resources():
    """Check available system resources"""
    force_garbage_collection()  # Force GC before checking memory
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent()
    
    logging.info(f"Available Memory: {memory.available / (1024 * 1024):.2f} MB")
    logging.info(f"CPU Usage: {cpu_percent}%")
    
    # Warning if available memory is less than 500MB (reduced threshold for mobile)
    if memory.available < (500 * 1024 * 1024):
        logging.warning("Critically low memory available!")
        return False
    return True

def time_str_to_seconds(time_str):
    h, m, s = time_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def read_timestamps(file_path, video_duration):
    timestamps = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if "-->" in line:
                    parts = line.strip().split("-->")
                    if len(parts) != 2:
                        continue
                    start_str, end_str = parts
                    try:
                        start_sec = time_str_to_seconds(start_str.strip())
                        end_sec = time_str_to_seconds(end_str.strip())

                        if start_sec >= video_duration:
                            continue
                        if end_sec > video_duration:
                            end_sec = video_duration

                        timestamps.append((start_sec, end_sec))
                    except ValueError as e:
                        logging.warning(f"Invalid timestamp format: {line.strip()}")
    except Exception as e:
        logging.error(f"Error reading timestamps: {str(e)}")
        raise
    return sorted(timestamps, key=lambda x: x[0])

def get_next_valid_timestamp(current_time, timestamps, min_gap=2):
    valid_timestamps = [(start, end) for start, end in timestamps if start >= current_time + min_gap]
    return valid_timestamps[0] if valid_timestamps else None

def apply_freeze_effect(video, current_time, timestamps):
    force_garbage_collection()  # Force GC before processing
    next_timestamp = get_next_valid_timestamp(current_time, timestamps, min_gap=2)
    if not next_timestamp:
        return None, None
    
    freeze_start = next_timestamp[0]
    freeze_duration = 3  # Reduced from 5 to 3 seconds to save memory
    
    if freeze_start + 0.1 >= video.duration:
        return None, None

    try:
        frozen_clip = freeze(video.subclip(freeze_start, min(freeze_start + 0.1, video.duration)), 
                           t=0, freeze_duration=freeze_duration)
        return frozen_clip, freeze_start + freeze_duration
    except Exception as e:
        logging.error(f"Error applying freeze effect: {str(e)}")
        return None, None

def apply_slow_motion_effect(video, current_time, timestamps):
    force_garbage_collection()  # Force GC before processing
    next_timestamp = get_next_valid_timestamp(current_time, timestamps)
    if not next_timestamp:
        return None, None
    
    slow_start = next_timestamp[0]
    slow_duration = 2  # Reduced from 4 to 2 seconds to save memory
    
    if slow_start + slow_duration >= video.duration:
        return None, None

    try:
        clip = video.subclip(slow_start, min(slow_start + slow_duration, video.duration))
        slowed_clip = clip.fx(vfx.speedx, factor=0.5)
        return slowed_clip, slow_start + slow_duration
    except Exception as e:
        logging.error(f"Error applying slow motion effect: {str(e)}")
        return None, None

def generate_normal_clip(video, current_time, timestamps):
    force_garbage_collection()  # Force GC before processing
    next_timestamp = get_next_valid_timestamp(current_time, timestamps)
    if not next_timestamp:
        return None, None
    
    start = next_timestamp[0]
    duration = random.uniform(2, 3)  # Reduced from 3-4 to 2-3 seconds
    
    if start + duration >= video.duration:
        return None, None

    try:
        return video.subclip(start, min(start + duration, video.duration)), start + duration
    except Exception as e:
        logging.error(f"Error generating normal clip: {str(e)}")
        return None, None

def apply_crossfade_transition(clip1, clip2, duration=0.3):  # Reduced transition duration
    """Menerapkan transisi crossfade antara dua klip."""
    try:
        clip1 = clip1.crossfadeout(duration)
        clip2 = clip2.crossfadein(duration)
        return CompositeVideoClip([clip1, clip2.set_start(clip1.duration - duration)])
    except Exception as e:
        logging.error(f"Error applying crossfade: {str(e)}")
        return clip1

def generate_recap(movie_path, timestamp_path, audio_path=None, resolution="480p", num_threads=1):
    if not check_system_resources():
        print("\nPeringatan: Sistem kekurangan resources untuk rendering!")
        print("Saran optimasi:")
        print("1. Tutup SEMUA aplikasi lain")
        print("2. Pastikan resolusi 480p")
        print("3. Gunakan 1 thread")
        print("4. Tunggu 1-2 menit agar sistem bisa membebaskan memory")
        
        while True:
            choice = input("\nLanjutkan proses? (y/n): ").lower()
            if choice == 'n':
                return
            elif choice == 'y':
                break

    video = None
    final_clip = None
    clips_with_transitions = []
    
    try:
        logging.info("Memulai proses video...")
        video = VideoFileClip(movie_path)
        timestamps = read_timestamps(timestamp_path, video.duration)

        current_time = 0
        total_duration = 0
        
        if audio_path:
            try:
                audio = AudioFileClip(audio_path)
                target_duration = min(audio.duration, 60)  # Limit to 60 seconds max
                audio.close()
            except Exception as e:
                logging.error(f"Error loading audio: {str(e)}")
                target_duration = min(video.duration, 60)  # Limit to 60 seconds max
        else:
            target_duration = min(video.duration, 60)  # Limit to 60 seconds max

        effect_counts = {'normal': 0, 'slow': 0, 'freeze': 0}
        total_clips = 0

        while total_duration < target_duration:
            if not check_system_resources():
                logging.warning("Memory hampir habis, mencoba membersihkan...")
                force_garbage_collection()
                if not check_system_resources():
                    print("\nMemory terlalu rendah untuk melanjutkan!")
                    break
                
            total_clips += 1
            percentages = {
                'normal': effect_counts['normal'] / total_clips if total_clips > 0 else 0,
                'slow': effect_counts['slow'] / total_clips if total_clips > 0 else 0,
                'freeze': effect_counts['freeze'] / total_clips if total_clips > 0 else 0
            }

            available_effects = []
            if percentages['normal'] < 0.6:  # Increased normal clip ratio
                available_effects.extend(['normal'] * 3)
            if percentages['slow'] < 0.2:  # Reduced special effects
                available_effects.append('slow')
            if percentages['freeze'] < 0.2:  # Reduced special effects
                available_effects.append('freeze')

            if not available_effects:
                available_effects = ['normal'] * 2 + ['slow', 'freeze']

            effect_type = random.choice(available_effects)
            
            try:
                if effect_type == 'slow':
                    clip, new_time = apply_slow_motion_effect(video, current_time, timestamps)
                    effect_counts['slow'] += 1
                elif effect_type == 'freeze':
                    clip, new_time = apply_freeze_effect(video, current_time, timestamps)
                    effect_counts['freeze'] += 1
                else:  # normal
                    clip, new_time = generate_normal_clip(video, current_time, timestamps)
                    effect_counts['normal'] += 1

                if clip is None or new_time is None:
                    break

                current_time = new_time
                total_duration += clip.duration
                clips_with_transitions.append(clip)
                
                # Log progress
                progress = (total_duration / target_duration) * 100
                logging.info(f"Progress: {progress:.1f}% (Memory: {psutil.virtual_memory().available / (1024*1024):.1f}MB)")
                
                # Clean up every few clips
                if len(clips_with_transitions) % 3 == 0:
                    force_garbage_collection()
                
            except Exception as e:
                logging.error(f"Error processing clip: {str(e)}")
                continue

        if not clips_with_transitions:
            raise Exception("Tidak dapat menghasilkan klip video yang cukup.")

        logging.info("Menggabungkan klip final...")
        # Reduce number of transitions to save memory
        transition_count = min(int(0.4 * (len(clips_with_transitions) - 1)), 5)
        transition_indices = random.sample(
            range(len(clips_with_transitions) - 1),
            transition_count
        )

        final_clips = []
        for i in range(len(clips_with_transitions)):
            if i < len(clips_with_transitions) - 1 and i in transition_indices:
                combined_clip = apply_crossfade_transition(
                    clips_with_transitions[i],
                    clips_with_transitions[i + 1]
                )
                final_clips.append(combined_clip)
                i += 1
            else:
                if i not in [x + 1 for x in transition_indices]:
                    final_clips.append(clips_with_transitions[i])

            # Clean up processed clips
            if i > 0:
                clips_with_transitions[i-1].close()
                force_garbage_collection()

        logging.info("Menggabungkan klip final...")
        final_clip = concatenate_videoclips(final_clips, method="compose")
        
        if total_duration > target_duration:
            final_clip = final_clip.subclip(0, target_duration)
        
        if audio_path:
            try:
                audio_clip = AudioFileClip(audio_path).subclip(0, target_duration)
                final_clip = final_clip.set_audio(audio_clip)
                audio_clip.close()
            except Exception as e:
                logging.error(f"Error setting audio: {str(e)}")

        logging.info("Mengubah resolusi video...")
        final_clip = final_clip.resize(newsize=(854, 480))  # Force 480p

        output_path = os.path.join(os.path.dirname(movie_path), "movie_recap_output.mp4")
        logging.info("Memulai proses rendering...")
        
        final_clip.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            threads=1,  # Force single thread
            fps=24,
            preset='ultrafast',  # Use fastest encoding preset
            logger=None
        )
        
        logging.info(f"Selesai! Video recap berhasil disimpan di: {output_path}")
        
    except Exception as e:
        logging.error(f"Terjadi kesalahan fatal: {str(e)}")
        print("\nTerjadi kesalahan dalam proses rendering.")
        print("Saran:")
        print("1. Tutup SEMUA aplikasi lain")
        print("2. Tunggu beberapa menit agar sistem bisa membebaskan memory")
        print("3. Coba render ulang dengan durasi yang lebih pendek")
        print("4. Cek file log untuk detail error")
    finally:
        try:
            # Clean up all resources
            if video:
                video.close()
            if final_clip:
                final_clip.close()
            for clip in clips_with_transitions:
                try:
                    clip.close()
                except:
                    pass
            force_garbage_collection()
        except Exception as e:
            logging.error(f"Error saat membersihkan resources: {str(e)}")

def find_files_recursive(directory, extensions):
    """Mencari file dengan ekstensi tertentu di direktori dan subdirektori"""
    files = []
    try:
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                if filename.lower().endswith(extensions):
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, directory)
                    files.append((rel_path, full_path))
    except Exception as e:
        logging.error(f"Error scanning files: {str(e)}")
    return sorted(files)

def get_file_path(prompt, file_type):
    while True:
        path = input(prompt).strip()
        if not path:
            return None
        if os.path.isfile(path):
            return path
        print(f"File tidak ditemukan: {path}")

def main():
    try:
        print("\nAuto Movie Recap - Command Line Version")
        print("======================================")
        
        # Dapatkan direktori saat ini
        current_dir = os.getcwd()
        
        # Input file movie
        print("\nPilih metode input file video:")
        print("1. Pilih dari daftar")
        print("2. Masukkan path manual")
        
        while True:
            choice = input("Pilihan (1/2): ").strip()
            if choice in ['1', '2']:
                break
            print("Pilihan tidak valid!")

        if choice == '1':
            print("\nMencari file video...")
            video_files = find_files_recursive(current_dir, ('.mp4', '.mov', '.avi'))
            if not video_files:
                print("Tidak ada file video di direktori ini dan subdirektorinya.")
                sys.exit(1)
            
            print("\nDaftar file video yang tersedia:")
            for i, (display_path, _) in enumerate(video_files, 1):
                print(f"{i}. {display_path}")
            
            while True:
                try:
                    choice = int(input("\nPilih nomor file video (1-%d): " % len(video_files)))
                    if 1 <= choice <= len(video_files):
                        _, movie_path = video_files[choice-1]
                        break
                    print("Pilihan tidak valid!")
                except ValueError:
                    print("Masukkan nomor yang valid!")
        else:
            movie_path = get_file_path("\nMasukkan path file video: ", "video")
            if not movie_path:
                print("Path file video tidak valid.")
                sys.exit(1)

        # Input file timestamp
        print("\nPilih metode input file timestamp:")
        print("1. Pilih dari daftar")
        print("2. Masukkan path manual")
        
        while True:
            choice = input("Pilihan (1/2): ").strip()
            if choice in ['1', '2']:
                break
            print("Pilihan tidak valid!")

        if choice == '1':
            print("\nMencari file timestamp...")
            timestamp_files = find_files_recursive(current_dir, '.txt')
            if not timestamp_files:
                print("Tidak ada file timestamp di direktori ini dan subdirektorinya.")
                sys.exit(1)
            
            print("\nDaftar file timestamp yang tersedia:")
            for i, (display_path, _) in enumerate(timestamp_files, 1):
                print(f"{i}. {display_path}")
            
            while True:
                try:
                    choice = int(input("\nPilih nomor file timestamp (1-%d): " % len(timestamp_files)))
                    if 1 <= choice <= len(timestamp_files):
                        _, timestamp_path = timestamp_files[choice-1]
                        break
                    print("Pilihan tidak valid!")
                except ValueError:
                    print("Masukkan nomor yang valid!")
        else:
            timestamp_path = get_file_path("\nMasukkan path file timestamp: ", "timestamp")
            if not timestamp_path:
                print("Path file timestamp tidak valid.")
                sys.exit(1)

        # Input file audio (opsional)
        print("\nPilih metode input file audio (opsional):")
        print("1. Pilih dari daftar")
        print("2. Masukkan path manual")
        print("3. Tidak menggunakan audio")
        
        while True:
            choice = input("Pilihan (1/2/3): ").strip()
            if choice in ['1', '2', '3']:
                break
            print("Pilihan tidak valid!")

        if choice == '3':
            audio_path = None
        elif choice == '1':
            print("\nMencari file audio...")
            audio_files = find_files_recursive(current_dir, ('.mp3', '.wav'))
            if not audio_files:
                print("Tidak ada file audio di direktori ini dan subdirektorinya.")
                audio_path = None
            else:
                print("\nDaftar file audio yang tersedia:")
                for i, (display_path, _) in enumerate(audio_files, 1):
                    print(f"{i}. {display_path}")
                print("0. Tidak menggunakan audio")
                
                while True:
                    try:
                        choice = int(input("\nPilih nomor file audio (0-%d): " % len(audio_files)))
                        if choice == 0:
                            audio_path = None
                            break
                        if 1 <= choice <= len(audio_files):
                            _, audio_path = audio_files[choice-1]
                            break
                        print("Pilihan tidak valid!")
                    except ValueError:
                        print("Masukkan nomor yang valid!")
        else:
            audio_path = get_file_path("\nMasukkan path file audio: ", "audio")

        # Mulai proses
        print("\nMemulai proses pembuatan recap...")
        # Force 480p dan 1 thread untuk stabilitas
        generate_recap(movie_path, timestamp_path, audio_path, "480p", 1)

    except Exception as e:
        logging.error(f"Error dalam main function: {str(e)}")
        print("\nTerjadi kesalahan yang tidak diharapkan.")
        print("Silakan cek file log untuk detail error.")

if __name__ == "__main__":
    main()
