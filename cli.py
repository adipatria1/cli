import os
import random
import sys
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, vfx, ImageClip, CompositeVideoClip
from moviepy.video.fx.freeze import freeze
from moviepy.video.fx.resize import resize
import numpy as np

def time_str_to_seconds(time_str):
    h, m, s = time_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def read_timestamps(file_path, video_duration):
    timestamps = []
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
                except ValueError:
                    print(f"Skipping invalid timestamp line: {line.strip()}")
    return sorted(timestamps, key=lambda x: x[0])

def get_next_valid_timestamp(current_time, timestamps, min_gap=2):
    valid_timestamps = [(start, end) for start, end in timestamps if start >= current_time + min_gap]
    return valid_timestamps[0] if valid_timestamps else None

def apply_freeze_effect(video, current_time, timestamps):
    next_timestamp = get_next_valid_timestamp(current_time, timestamps, min_gap=2)
    if not next_timestamp:
        return None, None
    
    freeze_start = next_timestamp[0]
    freeze_duration = 5  # Fixed 5 seconds for freeze effect
    
    if freeze_start + 0.1 >= video.duration:
        return None, None

    frozen_clip = freeze(video.subclip(freeze_start, min(freeze_start + 0.1, video.duration)), 
                        t=0, freeze_duration=freeze_duration)
    
    return frozen_clip, freeze_start + freeze_duration

def apply_slow_motion_effect(video, current_time, timestamps):
    next_timestamp = get_next_valid_timestamp(current_time, timestamps)
    if not next_timestamp:
        return None, None
    
    slow_start = next_timestamp[0]
    slow_duration = 4  # Fixed 4 seconds for slow motion
    
    if slow_start + slow_duration >= video.duration:
        return None, None

    clip = video.subclip(slow_start, min(slow_start + slow_duration, video.duration))
    slowed_clip = clip.fx(vfx.speedx, factor=0.5)  # Slow motion effect
    return slowed_clip, slow_start + slow_duration

def generate_normal_clip(video, current_time, timestamps):
    next_timestamp = get_next_valid_timestamp(current_time, timestamps)
    if not next_timestamp:
        return None, None
    
    start = next_timestamp[0]
    duration = random.uniform(3, 4)
    
    if start + duration >= video.duration:
        return None, None

    return video.subclip(start, min(start + duration, video.duration)), start + duration

def apply_crossfade_transition(clip1, clip2, duration=0.5):
    """Menerapkan transisi crossfade antara dua klip."""
    clip1 = clip1.crossfadeout(duration)
    clip2 = clip2.crossfadein(duration)
    return CompositeVideoClip([clip1, clip2.set_start(clip1.duration - duration)])

def generate_recap(movie_path, timestamp_path, audio_path=None, resolution="720p", num_threads=1):
    try:
        print("Memproses video...")
        video = VideoFileClip(movie_path)
        timestamps = read_timestamps(timestamp_path, video.duration)

        clips_with_transitions = []
        current_time = 0
        total_duration = 0
        target_duration = AudioFileClip(audio_path).duration if audio_path else video.duration

        # Track effect counts for balanced distribution
        effect_counts = {'normal': 0, 'slow': 0, 'freeze': 0}
        total_clips = 0

        while total_duration < target_duration:
            total_clips += 1
            percentages = {
                'normal': effect_counts['normal'] / total_clips if total_clips > 0 else 0,
                'slow': effect_counts['slow'] / total_clips if total_clips > 0 else 0,
                'freeze': effect_counts['freeze'] / total_clips if total_clips > 0 else 0
            }

            available_effects = []
            if percentages['normal'] < 0.5:
                available_effects.extend(['normal'] * 2)
            if percentages['slow'] < 0.25:
                available_effects.append('slow')
            if percentages['freeze'] < 0.25:
                available_effects.append('freeze')

            if not available_effects:
                available_effects = ['normal', 'slow', 'freeze']

            effect_type = random.choice(available_effects)
            
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

        if not clips_with_transitions:
            raise Exception("Tidak dapat menghasilkan klip video yang cukup.")

        final_clips = []
        transition_indices = random.sample(
            range(len(clips_with_transitions) - 1),
            int(0.6 * (len(clips_with_transitions) - 1))
        )

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

        final_clip = concatenate_videoclips(final_clips, method="compose")
        
        if total_duration > target_duration:
            final_clip = final_clip.subclip(0, target_duration)
        
        if audio_path:
            audio_clip = AudioFileClip(audio_path).subclip(0, target_duration)
            final_clip = final_clip.set_audio(audio_clip)

        if resolution == "720p":
            final_clip = final_clip.resize(newsize=(1280, 720))
        else:  # 480p
            final_clip = final_clip.resize(newsize=(854, 480))

        output_path = os.path.join(os.path.dirname(movie_path), "movie_recap_output.mp4")
        print("Rendering video recap, mohon tunggu...")
        
        final_clip.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            threads=num_threads,
            fps=24
        )
        
        print(f"Selesai! Video recap berhasil disimpan di: {output_path}")
        
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
    finally:
        if 'video' in locals():
            video.close()
        if 'final_clip' in locals():
            final_clip.close()

def find_files_recursive(directory, extensions):
    """Mencari file dengan ekstensi tertentu di direktori dan subdirektori"""
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.lower().endswith(extensions):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, directory)
                files.append((rel_path, full_path))
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

    # Pilih resolusi
    print("\nPilih resolusi output:")
    print("1. 720p (1280x720)")
    print("2. 480p (854x480)")
    while True:
        resolution_choice = input("Masukkan pilihan (1/2): ")
        if resolution_choice in ['1', '2']:
            resolution = "720p" if resolution_choice == '1' else "480p"
            break
        print("Pilihan tidak valid!")

    # Pilih jumlah threads
    print("\nPilih jumlah threads untuk rendering:")
    print("1. 1 thread (lambat tapi stabil)")
    print("2. 2 threads")
    print("3. 4 threads")
    print("4. 8 threads (cepat tapi membutuhkan lebih banyak RAM)")
    
    thread_options = {
        '1': 1,
        '2': 2,
        '3': 4,
        '4': 8
    }
    
    while True:
        thread_choice = input("Masukkan pilihan (1/2/3/4): ")
        if thread_choice in thread_options:
            num_threads = thread_options[thread_choice]
            break
        print("Pilihan tidak valid!")

    # Mulai proses
    print("\nMemulai proses pembuatan recap...")
    generate_recap(movie_path, timestamp_path, audio_path, resolution, num_threads)

if __name__ == "__main__":
    main()
