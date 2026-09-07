% Optional bridge: launch the independent desktop simulator from MATLAB.
% Python with tkinter is required. This is not a native Simulink model.
folder = fileparts(mfilename('fullpath'));
if ispc
    system(sprintf('start "" "%s"',fullfile(folder,'START_WINDOWS.bat')));
else
    system(sprintf('python3 "%s" &',fullfile(folder,'app.py')));
end
