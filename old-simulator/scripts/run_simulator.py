import os
import sys
import argparse
import pygame
from PIL import Image

# Add src to system path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__))))
from src.render.pygame_view import SimulatorApp

def make_gif(frame_dir, output_path, duration=250):
    """
    Stitches frames saved in frame_dir into a single animated GIF.
    """
    print(f"Stitching frames from {frame_dir} into {output_path}...")
    files = sorted(
        [os.path.join(frame_dir, f) for f in os.listdir(frame_dir) if f.startswith("frame_") and f.endswith(".bmp")],
        key=lambda x: int(os.path.basename(x).split("_")[1].split(".")[0])
    )
    
    if not files:
        print("Error: No frame files found to stitch.")
        return
        
    frames = [Image.open(f) for f in files]
    
    # Save as animated GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0
    )
    print(f"Animation saved successfully! ({len(frames)} frames)")
    
    # Convert GIF to MP4 if ffmpeg is available
    import shutil
    import subprocess
    if shutil.which("ffmpeg"):
        output_mp4 = os.path.splitext(output_path)[0] + ".mp4"
        print(f"Converting GIF to MP4 using ffmpeg: {output_mp4}...")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", output_path,
                "-movflags", "faststart",
                "-pix_fmt", "yuv420p",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                output_mp4
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("MP4 converted successfully!")
        except Exception as e:
            print(f"Failed to convert GIF to MP4: {e}")
    
    # Clean up files
    for f in files:
        try:
            os.remove(f)
        except Exception as e:
            print(f"Could not remove temporary file {f}: {e}")
    try:
        os.rmdir(frame_dir)
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="Run the Rule 184 Traffic Simulator")
    parser.add_argument("--density", type=float, default=0.3, help="Initial density of vehicles (0.0 to 1.0)")
    parser.add_argument("--length", type=int, default=1000, help="Road length in cells")
    parser.add_argument("--speed", type=int, default=10, help="Simulation steps per second")
    parser.add_argument("--case", type=int, default=1, choices=[1, 2, 3, 4, 5], help="Lane/junction configuration case (1-5)")
    parser.add_argument("--record", action="store_true", help="Auto-record zoom/pan sequence and generate demonstration GIF and MP4")
    
    args = parser.parse_args()
    
    # If recording, default to Case 5 (connected network) unless case was explicitly requested
    if args.record and not any(arg.startswith("--case") for arg in sys.argv):
        args.case = 5
        
    # Validate arguments
    if not (0.0 <= args.density <= 1.0):
        print("Error: Density must be between 0.0 and 1.0")
        sys.exit(1)
        
    if args.length <= 0:
        print("Error: Road length must be greater than 0")
        sys.exit(1)
        
    if args.record:
        print(f"Starting simulator in RECORDING mode for Case {args.case}...")
        # Run in recording mode
        app = SimulatorApp(
            road_length=args.length,
            target_density=args.density,
            steps_per_second=args.speed,
            case=args.case
        )
        
        # Temp dir for frames
        temp_frame_dir = "temp_frames"
        os.makedirs(temp_frame_dir, exist_ok=True)
        
        frame_count = 0
        # For case 5 we want 30 seconds of activity (120 frames at 250ms)
        max_record_frames = 120 if args.case == 5 else 60
        last_record_time = 0
        record_interval_ms = 250 # 250ms interval
        
        start_ticks = pygame.time.get_ticks()
        
        while app.running and frame_count < max_record_frames:
            # Handle standard events
            app.handle_events()
            app.update()
            
            # Programmatic interaction sequences to demonstrate features
            current_ticks = pygame.time.get_ticks()
            elapsed_sec = (current_ticks - start_ticks) / 1000.0
            
            # Interactive sequence demonstrations:
            # 1. 0s to 5s: Normal run
            # 2. 5s to 10s: Zoom in
            if 5.0 <= elapsed_sec < 10.0:
                app.zoom(1.03, app.width / 2.0, app.height / 2.0)
            # 3. 10s to 20s: Pan right and down
            elif 20.0 > elapsed_sec >= 10.0:
                app.camera_x += 4.0
                app.camera_y += 2.0
            # 4. 20s to 25s: Zoom back out
            elif 25.0 > elapsed_sec >= 20.0:
                app.zoom(1.0 / 1.03, app.width / 2.0, app.height / 2.0)
            # 5. 25s onwards: Normal run
            
            app.draw()
            
            # Record frame
            if current_ticks - last_record_time >= record_interval_ms:
                frame_path = os.path.join(temp_frame_dir, f"frame_{frame_count}.bmp")
                pygame.image.save(app.screen, frame_path)
                frame_count += 1
                last_record_time = current_ticks
                print(f"Recorded frame {frame_count}/{max_record_frames}", end='\r')
                
            app.clock.tick(60)
            
        pygame.quit()
        print()
        
        # Make notebooks/figures/ directory if needed
        output_dir = os.path.join("notebooks", "figures")
        os.makedirs(output_dir, exist_ok=True)
        
        # Select correct filename based on case
        if args.case == 5:
            output_name = "phase3_junction_demo.gif"
        elif args.case == 1:
            output_name = "phase2_demo.gif"
        else:
            output_name = f"case_{args.case}_demo.gif"
            
        output_gif = os.path.join(output_dir, output_name)
        make_gif(temp_frame_dir, output_gif, duration=record_interval_ms)
        
    else:
        # Standard interactive execution
        app = SimulatorApp(
            road_length=args.length,
            target_density=args.density,
            steps_per_second=args.speed,
            case=args.case
        )
        app.run()

if __name__ == "__main__":
    main()
