import logging
import os

import numpy as np
import random
import pandas as pd
from scipy import misc, ndimage

from config import pathDict, fileNames
from data_transformation.data_io import dumpPickleFile, getPickleFile

logging.basicConfig(level=logging.DEBUG, filename="logfile.log", filemode="w",
                    format="%(asctime)-15s %(levelname)-8s %(message)s")


def zero_pad(inp, out_shape):
    m, n, c = inp.shape
    out_m, out_n, out_c = out_shape

    to_pad_m = max(out_m - m, 0)
    to_pad_n = max(out_n - n, 0)
    to_pad_c = max(out_c - c, 0)
    
    pad_m1 = to_pad_m // 2
    pad_m2 = to_pad_m - pad_m1
    
    pad_n1 = to_pad_n // 2
    pad_n2 = to_pad_n - pad_n1
    
    pad_c1 = to_pad_c // 2
    pad_c2 = to_pad_c - pad_c1
    
    inp = np.pad(inp, ((pad_m1, pad_m2), (pad_n1, pad_n2), (pad_c1, pad_c2)), 'constant')
    return inp


def resize_image(image, resize_shape, path=None):
    # logging.info('Images reshaped to: %s', str(resize_shape))
    if image.shape[0] < resize_shape[0] or image.shape[1] < resize_shape[1]:
        image = zero_pad(inp=image, out_shape=resize_shape)
    
    image_rsized = misc.imresize(image, resize_shape)
    image_rsized = np.array(image_rsized)

    return image_rsized




def get_dump_image_given_path(paths, img_resize_shape, img_per_label_per_batch, label_dict, labels, outpath, filename):
    dataBatchX = np.ndarray(shape=(len(paths),
                                   img_resize_shape[0],
                                   img_resize_shape[1], 3), dtype='float32')
    for num, pic_path in enumerate(paths):
        image = ndimage.imread(pic_path, mode='RGB')
        image = resize_image(image, img_resize_shape, pic_path)
        dataBatchX[num,:] = image
    
    dataBatchY = np.append(
            np.tile(float(labels[0]), img_per_label_per_batch),
            np.tile(float(labels[1]), img_per_label_per_batch))
    
    dumpPickleFile(dataX=dataBatchX,
                   dataY=dataBatchY,
                   labelDict=label_dict,
                   folderPath=outpath,
                   picklefileName=filename)


def genStratifiedBatches(img_resize_shape, valid_land_pins, valid_house_pins, cv_batch_size, tr_batch_size, image_type='aerial', dump=True, shuffle_seed=873):
    
    if image_type not in ['assessor', 'google_aerial', 'bing_aerial', 'streetside']:
        raise ValueError('Variable image_type not understood')
    
    land_image_path = os.path.join(pathDict['%s_image_path' % (image_type)], 'land')
    house_image_path = os.path.join(pathDict['%s_image_path' % (image_type)], 'house')
    output_batch_path = pathDict['%s_batch_path' % (image_type)]

    logging.info('Input Land Images from %s: ', str(land_image_path))
    logging.info('Input House Images from %s: ', str(house_image_path))
    logging.info('Output batch array to %s: ', str(output_batch_path))
    
    land_label = 0
    house_label = 1
    label_dict = {'0': 'land', '1': 'house'}
    land_pins = np.sort(np.intersect1d(
        np.array([img.split('.')[0] for img in os.listdir(land_image_path) if img != '.DS_Store'], dtype=str),
        valid_land_pins))
    
    house_pins = np.sort(np.intersect1d(
            np.array([img.split('.')[0] for img in os.listdir(house_image_path) if img != '.DS_Store'], dtype=str),
            valid_house_pins))
    
    my_seed = shuffle_seed
    np.random.seed(my_seed)
    np.random.shuffle(land_pins)
    np.random.shuffle(house_pins)

    logging.info('Input Data: Total Land: %s, Total House: %s', str(len(land_pins)), str(len(house_pins)))
    
    ####################################################################################
    # Create the first batch as Validation and then remove the validation data from the actual dataset. This is done to ensure that the none of the validation data falls under the training batches
    cv_img_per_label_per_batch = cv_batch_size // 2
    valid_land_pins = land_pins[0: cv_img_per_label_per_batch]
    valid_house_pins = house_pins[0: cv_img_per_label_per_batch]
    
    # New land pins, and house_pins
    train_land_pins = land_pins[cv_img_per_label_per_batch: ]
    train_house_pins = house_pins[cv_img_per_label_per_batch:]

    paths = [os.path.join(land_image_path, pin + '.jpg') for pin in valid_land_pins] + \
            [os.path.join(house_image_path, pin + '.jpg') for pin in valid_house_pins]
        
    # LOAD THE VALIDATION SET TO THE DISK
    if dump:
        get_dump_image_given_path(paths, img_resize_shape,
                                  cv_img_per_label_per_batch, label_dict,
                                  labels=[land_label,house_label],
                                  outpath=output_batch_path,
                                  filename='cv.pickle')
    
    logging.info('Validation Land Size: %s, Validation House Size: %s, Training Land Size: %s, Training House Size: %s', str(len(valid_land_pins)), str(len(valid_house_pins)), str(len(train_land_pins)), str(len(train_house_pins)))

    ####################################################################################

    tr_img_per_label_per_batch = tr_batch_size // 2

    if len(train_land_pins) > len(train_house_pins):
        bigger, b_label = train_land_pins, land_label
        smaller, s_label = train_house_pins, house_label
        b_land, b_house = True, False
    else:
        bigger, b_label = train_house_pins, house_label
        smaller, s_label = train_land_pins, land_label
        b_house, b_land = True, False


    num_batches = int(np.ceil(len(bigger) / tr_img_per_label_per_batch))

    count = 1
    pin_batch_row_meta = None
    for batch_num in range(0, num_batches):
        logging.info('Creating BATCH %s .......... ', str(batch_num))
        idx1 = batch_num * tr_img_per_label_per_batch
        idx2 = batch_num * tr_img_per_label_per_batch + tr_img_per_label_per_batch

        if len(bigger) >= idx2:
            logging.info('Bigger: len(bigger) >= idx2 ')
            b_batch_pins = bigger[idx1: idx2]
        elif len(bigger) > idx1 and len(bigger) < idx2:
            logging.info('Bigger: idx1 < len(bigger) < idx2 ')
            b_batch_pins = bigger[idx1:len(bigger)]
            how_many = idx2 - len(bigger)
            random.seed(my_seed + count)
            b_idx = random.sample(range(0, len(bigger)), how_many)
            b_batch_pins = np.append(b_batch_pins, bigger[b_idx])
            count += 1
        else:
            logging.info('Bigger: len(bigger) < idx1 < idx2 ')
            how_many = tr_img_per_label_per_batch
            random.seed(my_seed + count)
            b_idx = random.sample(range(0, len(bigger)), how_many)
            b_batch_pins = smaller[b_idx]
            count += 1

        if len(smaller) >= idx2:
            logging.info('Smaller: len(Smaller) >= idx2 ')
            s_batch_pins = smaller[idx1: idx2]
        elif len(smaller) > idx1 and len(smaller) < idx2:
            logging.info('Smaller: idx1 < len(Smaller) < idx2 ')
            s_batch_pins = smaller[idx1:len(smaller)]
            how_many = idx2 - len(smaller)
            random.seed(my_seed + count)
            s_idx = random.sample(range(0, len(smaller)), how_many)
            s_batch_pins = np.append(s_batch_pins, smaller[s_idx])
            count += 1
        else:
            logging.info('Smaller: len(Smaller) < idx1 < idx2 ')
            how_many = tr_img_per_label_per_batch
            random.seed(my_seed + count)
            s_idx = random.sample(range(0, len(smaller)), how_many)
            s_batch_pins = smaller[s_idx]
            count += 1

        # GET IMAGE PATH
        if b_land:
            paths = [os.path.join(land_image_path, pin + '.jpg') for pin in b_batch_pins] + [
                os.path.join(house_image_path, pin + '.jpg') for pin in s_batch_pins]
            label = np.array(['land'] * len(b_batch_pins) + ['house'] * len(s_batch_pins))
        else:
            paths = [os.path.join(house_image_path, pin + '.jpg') for pin in b_batch_pins] + [
                os.path.join(land_image_path, pin + '.jpg') for pin in s_batch_pins]
            label = np.array(['house'] * len(b_batch_pins) + ['land'] * len(s_batch_pins))

        # We would like to create a metadata table that hods the list of pins and their corresponding batch number
        # and record number, so that we can perform some testing and validation.
        pins = np.vstack((b_batch_pins.reshape(-1, 1), s_batch_pins.reshape(-1, 1)))
        batch_no = np.tile(batch_num, len(pins))
        rownum = np.arange(len(batch_no))

        if batch_num == 0:
            pin_batch_row_meta = np.column_stack(
                    (pins, batch_no.reshape(-1, 1), rownum.reshape(-1, 1), label.reshape(-1, 1)))
        else:
            pin_batch_row_meta = np.vstack((pin_batch_row_meta,
                                            np.column_stack((pins, batch_no.reshape(-1, 1), rownum.reshape(-1, 1),
                                                             label.reshape(-1, 1)))))


        if dump:
            get_dump_image_given_path(paths, img_resize_shape,
                                      tr_img_per_label_per_batch, label_dict,
                                      labels=[b_label, s_label],
                                      outpath=output_batch_path,
                                      filename='tr%s.pickle'%str(batch_num))

    if dump:
        # DUMP THE PIN_BATCH_ROW_META
        pin_batch_row_meta = pd.DataFrame(pin_batch_row_meta, columns=['pin', 'batch_no', 'rownum', 'indicator'])
        pin_batch_row_meta.to_csv(
            os.path.join(pathDict['pin_batch_row_meta_path'], '%s_pin_batch_row_meta.csv' % (image_type)),
            index=None)
    
    
        
debugg = False
if debugg:
    valid_land_pins = np.array(['30-07-132-018-0000', '29-36-102-064-0000', '24-33-100-102-0000',
     '31-34-404-016-0000', '24-04-427-016-0000', '18-04-236-010-0000',
     '28-22-315-044-0000', '30-07-102-004-0000', '16-32-405-054-0000',
     '29-36-101-023-0000', '29-36-101-022-0000', '01-13-101-026',
     '30-07-108-009-0000', '31-34-402-001-0000', '30-30-107-003-0000',
     '19-01-311-005-0000', '17-31-104-037-0000', '28-22-315-032-0000',
     '26-30-404-045-0000', '26-30-404-044-0000', '29-16-118-084-0000',
     '31-34-403-029-0000', '05-10-411-007', '06-36-307-008-0000',
     '31-35-331-009-0000', '29-25-400-117-0000', '17-31-302-013-0000'], dtype=str)


    valid_house_ids = np.array( ['14-33-108-015', '29-04-203-032-0000',
                                 '11-20-218-024', '16-23-304-011',
     '16-34-212-014' ,'16-10-411-005-0000' ,'16-23-304-005' ,'15-10-100-043',
     '20-18-221-030-0000', '26-07-302-005-0000' ,'09-26-101-015' ,'08-29-207-029',
     '16-18-102-001' ,'20-20-311-006-0000', '07-01-210-021', '16-11-102-002',
     '11-31-116-012' ,'07-19-402-001', '16-08-402-009', '09-13-208-007',
     '09-35-103-010' ,'13-34-201-039', '21-31-400-005-0000' ,'29-24-100-018-1035',
     '17-09-124-020-1222', '07-15-202-002' ,'06-27-406-020', '08-29-220-010',
     '14-05-301-001', '13-26-101-001' ,'08-32-429-025' ,'09-36-109-002',
     '06-17-421-013', '08-19-106-006' '07-07-407-006' '06-18-303-008',
     '25-27-126-013-0000' ,'25-22-306-060-0000' ,'30-17-107-043-0000',
     '09-24-206-042' ,'05-23-200-043' ,'07-15-206-036' ,'04-28-216-008',
     '01-33-100-603' ,'13-01-100-013', '32-25-307-021-0000' ,'10-25-204-015',
     '10-24-412-005', '07-26-419-018', '31-04-404-011-0000' ,'31-02-204-170-0000',
     '08-04-111-001', '29-32-406-043-1219', '09-25-102-004', '29-19-413-054-0000',
     '08-16-335-003', '20-24-430-011-1113' ,'22-33-400-011-0000' ,'07-02-102-028'
     '08-21-324-003' ,'13-28-400-005' ,'14-33-205-001', '18-13-223-020-0000',
     '11-29-401-020', '11-21-309-013', '30-20-304-061-0000', '20-02-303-040-0000',
     '05-23-200-042', '11-29-306-010' ,'04-16-412-015', '30-17-103-004-0000','07-06-303-011'])

    genStratifiedBatches([224, 224], valid_land_pins, valid_house_ids, cv_batch_size=100, tr_batch_size=20, image_type='aerial',
                               dump=True)